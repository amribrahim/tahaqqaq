"""Human-review requests that carry the verification report as a PDF.

The person asks for a review with their name and email. The server renders the report it produced itself (reports are
kept in memory for RECENT_HOURS after the verification; an older one is verified again from its text), so a PDF can
never carry a verdict the tool did not give. The PDF is kept for RETAIN_DAYS so the reviewer can open it from the
email link, then deleted. The email itself is sent from the browser through the site's Web3Forms contact form, because
Web3Forms' free plan accepts browser submissions only and has no file attachments: the message carries the link."""
from __future__ import annotations

import html
import logging
import secrets
import threading
import time
from collections import OrderedDict
from datetime import datetime
from urllib.parse import urlparse

log = logging.getLogger(__name__)

RECENT_HOURS = 6
RECENT_MAX = 300
RETAIN_DAYS = 14
TOKEN_BYTES = 24

_recent: OrderedDict[str, tuple[float, dict]] = OrderedDict()
_lock = threading.Lock()
_table_ready = False

STATE_LABELS = {
    "verified": ("مؤيَّد بمصدر", "Confirmed by source"),
    "partial": ("مؤيَّد جزئيًا – اختلاف رواية", "Partially confirmed – variant wording"),
    "uncertain": ("غير مؤكد", "Unconfirmed"),
    "abstain": ("لا مرجع – يُمتنع عن الحكم", "No reference – verdict withheld"),
    "referral": ("مسألة شخصية تستوجب فتوى – إحالة", "Personal matter – referred for a fatwa"),
    "unreliable": ("وُجد النص وحكمه منقول أدناه", "Found; the recorded ruling is quoted below"),
}
STATE_COLORS = {"verified": "#087a62", "partial": "#2f6fd6", "uncertain": "#b26a00", "abstain": "#5a5d80",
                "referral": "#5a5d80", "unreliable": "#b42318"}


# -- reports the server produced -----------------------------------------------------------------
def remember(report: dict) -> None:
    """Keep a report the pipeline just produced, so a review request can render exactly what the person saw."""
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


# -- rendering -----------------------------------------------------------------------------------
def _e(s: object) -> str:
    return html.escape(str(s or ""))


def _dir(text: object) -> str:
    """The direction of a block from its own letters (WeasyPrint does not implement dir="auto")."""
    t = str(text or "")
    arabic = sum(1 for ch in t if "\u0600" <= ch <= "\u06ff")
    latin = sum(1 for ch in t if ch.isascii() and ch.isalpha())
    return "rtl" if arabic >= latin else "ltr"


def _row(label: str, value: str, ltr: bool = False) -> str:
    if not value:
        return ""
    return f'<tr><th>{_e(label)}</th><td{" dir=ltr class=ltr" if ltr else f" dir={_dir(value)}"}>{_e(value)}</td></tr>'


def _link_row(label: str, url: str) -> str:
    """A source link as its site name, clickable in the PDF (the full address of a search link is unreadable)."""
    if not url:
        return ""
    site = urlparse(url).netloc.removeprefix("www.") or url
    return f'<tr><th>{_e(label)}</th><td dir=ltr class=ltr><a href="{_e(url)}">{_e(site)} ↗</a></td></tr>'


def render_html(report: dict, lang: str, name: str, email: str) -> str:
    ar = lang == "ar"
    L = (lambda a, b: a if ar else b)  # noqa: E731 - label picker
    state = report.get("state", "abstain")
    label = STATE_LABELS.get(state, (state, state))[0 if ar else 1]
    src, grade = report.get("source") or {}, report.get("grade") or {}
    when = (report.get("created_at") or datetime.utcnow().isoformat())[:16].replace("T", " ")
    parts = [f"""<header><div class="brand">{L("تحقّق", "Tahaqqaq")}</div>
<div class="title">{L("تقرير التحقق — طلب مراجعة بشرية", "Verification report — human review request")}</div>
<div class="meta">{_e(when)} UTC · {L("رقم التقرير", "Report")} <span dir="ltr">{_e(report.get("id"))}</span></div></header>"""]
    parts.append(f'<section class="box"><h2>{L("مقدّم الطلب", "Requested by")}</h2><table>'
                 + _row(L("الاسم", "Name"), name) + _row(L("البريد", "Email"), email, ltr=True) + "</table></section>")
    parts.append(f'<section class="state" style="border-color:{STATE_COLORS.get(state, "#5a5d80")}">'
                 f'<div class="state-label" style="color:{STATE_COLORS.get(state, "#5a5d80")}">{_e(label)}</div>'
                 f'<div class="conf">{L("نسبة التطابق", "Match")}: <span dir="ltr">{_e(report.get("confidence"))}%</span></div>'
                 f'<p dir="{"rtl" if ar else "ltr"}">{_e(report.get("reason_ar") if ar else report.get("reason_en"))}</p></section>')
    parts.append(f'<section class="box"><h2>{L("النص المُدخل", "Text submitted")}</h2>'
                 f'<p class="quote" dir="{_dir(report.get("input_text"))}">{_e(report.get("input_text"))}</p></section>')
    mt = report.get("machine_translation")
    if mt:
        parts.append(f'<section class="box"><h2>{L("ترجمة آلية للمطابقة فقط", "Machine translation, for matching only")}'
                     f' · {_e(mt.get("language"))}</h2><p dir="ltr" class="ltr">{_e(mt.get("english"))}</p></section>')
    if src:
        rows = (_row(L("المصدر", "Source"), src.get("book_ar") if ar else src.get("book_en"))
                + _row(L("الرقم", "Number"), src.get("number"), ltr=True)
                + _row(L("الباب", "Chapter"), src.get("chapter_ar") if ar else src.get("chapter_en") or src.get("chapter_ar"))
                + _link_row(L("الرابط", "Link"), src.get("source_url")))
        heading = L("أقرب نص (للمقارنة فقط)", "Closest text (for comparison only)") if report.get("closest_only") else L("النص في المصدر", "Text in the source")
        body = f'<p class="quote" dir="rtl">{_e(src.get("matn_ar") or src.get("text_ar"))}</p>' if src.get("matn_ar") or src.get("text_ar") else ""
        if src.get("text_en"):
            body += f'<p class="ltr en" dir="ltr">{_e(src.get("text_en"))}</p>'
        parts.append(f'<section class="box"><h2>{heading}</h2><table>{rows}</table>{body}</section>')
    if grade:
        rows = "".join(_row(g.get("grader_ar") if ar else g.get("grader_en") or g.get("grader_ar"),
                            g.get("grade_ar") if ar else g.get("grade_en") or g.get("grade_ar"))
                       for g in (report.get("grades") or [grade]))
        parts.append(f'<section class="box"><h2>{L("الحكم كما ورد في المصدر", "Ruling as recorded in the source")}</h2>'
                     f'<table>{rows}</table></section>')
    narr = report.get("narrations") or []
    if narr:
        def grade_of(n: dict) -> str:
            g = n.get("grade_ar") if ar else n.get("grade_en") or n.get("grade_ar")
            return f" — {_e(g)}" if g else ""

        items = "".join(f'<li>{_e(n.get("book_ar") if ar else n.get("book_en"))} <span dir="ltr">{_e(n.get("number"))}</span>{grade_of(n)}</li>'
                        for n in narr[:8])
        parts.append(f'<section class="box"><h2>{L("روايات أخرى للنص نفسه", "Other narrations of the same text")}</h2><ul>{items}</ul></section>')
    cands = [c for c in report.get("candidates") or [] if not c.get("accepted")][:4]
    if cands:
        items = "".join(f'<li>{_e(c.get("book_ar") if ar else c.get("book_en"))} <span dir="ltr">{_e(c.get("number"))}'
                        f' · {_e(c.get("confidence"))}%</span><div class="cand" dir="{_dir(c.get("text_ar") or c.get("text_en"))}">{_e((c.get("text_ar") or c.get("text_en") or "")[:220])}</div></li>'
                        for c in cands)
        parts.append(f'<section class="box"><h2>{L("نتائج قريبة أخرى", "Other close results")}</h2><ul>{items}</ul></section>')
    if report.get("ai_explanation"):
        parts.append(f'<section class="box ai"><h2>{L("شرح مولَّد بالذكاء الاصطناعي", "AI-generated explanation")}'
                     f' · <span dir="ltr">{_e(report.get("ai_model"))}</span></h2><p dir="{_dir(report.get("ai_explanation"))}">{_e(report.get("ai_explanation"))}</p></section>')
    parts.append(f'<footer>{L("ننقل أحكام المحدّثين من مصادرها، ولا نُصدر حكمًا آليًا.", "We relay the scholars’ rulings from their sources; the tool issues no ruling of its own.")}'
                 f' · <span dir="ltr">tahaqqaq.pages.dev</span></footer>')
    return f"""<!doctype html><html lang="{lang}" dir="{"rtl" if ar else "ltr"}"><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 16mm 14mm; @bottom-center {{ content: counter(page) " / " counter(pages); direction: ltr; font: 9pt "DejaVu Sans", sans-serif; color: #8a8db0; }} }}
body {{ font-family: "Amiri", "Noto Naskh Arabic", "DecoType Naskh", "DejaVu Sans", serif; color: #1d1f3d; font-size: {"13pt" if ar else "12pt"}; line-height: 1.7; }}
header {{ border-bottom: 2px solid #4f3fd0; padding-bottom: 8px; margin-bottom: 14px; }}
.brand {{ font-size: 22pt; font-weight: bold; color: #4f3fd0; }}
.title {{ font-size: 14pt; font-weight: bold; }}
.meta {{ font-size: 9.5pt; color: #5a5d80; }}
h2 {{ font-size: 11.5pt; color: #4f3fd0; margin: 0 0 6px; }}
.box {{ border: 1px solid #e4e1f5; border-radius: 8px; padding: 10px 12px; margin: 0 0 10px; }}
h2 {{ break-after: avoid; }}
tr, li {{ break-inside: avoid; }}
[dir=ltr] {{ text-align: left; }}
[dir=rtl] {{ text-align: right; }}
.state {{ border: 2px solid; border-radius: 8px; padding: 10px 12px; margin: 0 0 10px; }}
.state-label {{ font-size: 15pt; font-weight: bold; }}
.conf {{ font-size: 10.5pt; color: #3d4066; }}
.state p {{ margin: 6px 0 0; font-size: 11pt; }}
.quote {{ font-size: 15pt; line-height: 1.9; margin: 6px 0; }}
.ltr {{ font-family: "DejaVu Sans", sans-serif; text-align: left; font-size: 10.5pt; line-height: 1.5; }}
td.ltr {{ text-align: {"right" if ar else "left"}; }}
.en {{ color: #3d4066; }}
table {{ border-collapse: collapse; width: 100%; font-size: 11pt; table-layout: fixed; }}
a {{ color: #4f3fd0; text-decoration: none; }}
th {{ text-align: start; color: #5a5d80; font-weight: normal; width: 26%; padding: 2px 0; vertical-align: top; }}
td {{ padding: 2px 0; overflow-wrap: anywhere; }}
p, li {{ overflow-wrap: anywhere; }}
ul {{ margin: 0; padding-inline-start: 18px; }}
li {{ margin: 0 0 4px; }}
.cand {{ font-size: 10.5pt; color: #3d4066; }}
.ai {{ border-style: dashed; background: #fbfaff; }}
[dir=ltr] {{ direction: ltr; unicode-bidi: embed; }}
footer {{ margin-top: 14px; padding-top: 8px; border-top: 1px solid #e4e1f5; font-size: 9.5pt; color: #5a5d80; }}
</style></head><body>{"".join(parts)}</body></html>"""


def render_pdf(report: dict, lang: str, name: str, email: str) -> bytes:
    from weasyprint import HTML  # lazy: needs the Pango system library

    return HTML(string=render_html(report, lang, name, email)).write_pdf()


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
