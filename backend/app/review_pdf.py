"""Human-review requests that carry the verification report as a PDF.

The PDF is the same document as the result page's "export PDF" button: a headless Chromium opens the site's own result
page with the report and prints it with the page's print layout. Only reports this server produced are printed (kept
in memory for RECENT_HOURS after the verification; an older one is verified again from its text), so a PDF can never
carry a verdict the tool did not give. The PDF is kept for RETAIN_DAYS so the reviewer can open it from the email link,
then deleted. The email itself is sent from the browser through the site's Web3Forms contact form, because Web3Forms'
free plan accepts browser submissions only and has no file attachments: the message carries the link."""
from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from collections import OrderedDict

from .config import get_settings

log = logging.getLogger(__name__)

RECENT_HOURS = 6
RECENT_MAX = 300
RETAIN_DAYS = 14
TOKEN_BYTES = 24
DEFAULT_TZ = "Asia/Riyadh"

_recent: OrderedDict[str, tuple[float, dict]] = OrderedDict()
_lock = threading.Lock()
_renders = threading.BoundedSemaphore(2)   # a browser takes ~200 MB: at most two prints at once
_table_ready = False


# -- reports the server produced -----------------------------------------------------------------
def remember(report: dict) -> None:
    """Keep a report the pipeline just produced, so a review request can print exactly what the person saw."""
    if not report.get("id"):
        return
    now = time.time()
    with _lock:
        _recent[report["id"]] = (now, report)
        _recent.move_to_end(report["id"])
        while _recent and (len(_recent) > RECENT_MAX or now - next(iter(_recent.values()))[0] > RECENT_HOURS * 3600):
            _recent.popitem(last=False)


def recall(report_id: str) -> dict | None:
    with _lock:
        hit = _recent.get(report_id or "")
    if not hit or time.time() - hit[0] > RECENT_HOURS * 3600:
        return None
    return hit[1]


# -- printing the result page --------------------------------------------------------------------
def page_setup(report: dict, lang: str) -> tuple[str, str]:
    """(result page URL, script run before the page loads). The script puts the report where the page keeps the
    reports it has shown (sessionStorage), so the page renders it as is, without verifying again."""
    rid = report["id"]
    url = f"{get_settings().frontend_url.rstrip('/')}/result/?id={rid}"
    stored = json.dumps({**report, "server_id": rid}, ensure_ascii=False)
    script = (f"sessionStorage.setItem({json.dumps('tahqaq.report.' + rid)}, {json.dumps(stored, ensure_ascii=False)});"
              f"localStorage.setItem('tahqaq.lang', {json.dumps(lang)});")
    return url, script


def time_zone(tz: str) -> str:
    """The person's IANA time zone when valid, else Saudi time (the times on the page are shown in local time)."""
    from zoneinfo import ZoneInfo

    try:
        ZoneInfo(tz)
        return tz
    except (ValueError, KeyError, OSError):
        return DEFAULT_TZ


def _launch_options() -> dict:
    path = get_settings().pdf_chromium_path or ("/usr/bin/chromium" if os.path.exists("/usr/bin/chromium") else "")
    opts: dict = {"args": ["--disable-dev-shm-usage"]}
    return {**opts, "executable_path": path} if path else {**opts, "channel": "chrome"}


def render_pdf(report: dict, lang: str, tz: str = DEFAULT_TZ) -> bytes:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright  # lazy: starts a browser driver

    url, script = page_setup(report, lang)
    with _renders, sync_playwright() as p:
        browser = p.chromium.launch(**_launch_options())
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 1800}, timezone_id=time_zone(tz),
                                    locale="ar-SA" if lang == "ar" else "en-GB")
            page.add_init_script(script=script)
            page.goto(url, wait_until="load", timeout=30_000)
            page.wait_for_selector("[data-testid=status-banner]", timeout=20_000)
            try:   # cards that load their own data (rulings from الدرر) appear as they do for the person
                page.wait_for_load_state("networkidle", timeout=12_000)
            except PlaywrightError:
                pass
            page.evaluate("document.fonts.ready.then(() => true)")
            return page.pdf(print_background=True, prefer_css_page_size=True)
        finally:
            browser.close()


# -- storage for the email link ------------------------------------------------------------------
def _ensure_table(conn) -> None:
    global _table_ready
    if not _table_ready:
        conn.execute("CREATE TABLE IF NOT EXISTS review_pdfs (token TEXT PRIMARY KEY, report_id TEXT NOT NULL, "
                     "pdf BYTEA NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())")
        _table_ready = True


def save(pdf: bytes, report_id: str) -> str:
    from . import db

    token = secrets.token_urlsafe(TOKEN_BYTES)
    with db.get_conn() as conn:
        _ensure_table(conn)
        conn.execute("DELETE FROM review_pdfs WHERE created_at < now() - make_interval(days => %s)", (RETAIN_DAYS,))
        conn.execute("INSERT INTO review_pdfs (token, report_id, pdf) VALUES (%s, %s, %s)", (token, report_id, pdf))
    return token


def load(token: str) -> tuple[bytes, str] | None:
    from . import db

    with db.get_conn() as conn:
        _ensure_table(conn)
        row = conn.execute("SELECT pdf, report_id FROM review_pdfs WHERE token = %s AND created_at >= now() - make_interval(days => %s)",
                           (token, RETAIN_DAYS)).fetchone()
    return (bytes(row["pdf"]), row["report_id"]) if row else None
