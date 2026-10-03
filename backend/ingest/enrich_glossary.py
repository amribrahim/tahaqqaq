"""Attach to each glossary term its entry in «الجمهرة — موسوعة مفردات المحتوى الإسلامي» (islamic-content.com),
one of the challenge's approved references: the Arabic definition as published there and the entry URL.
Best effort: terms without a matching entry keep their seed text and are flagged in the report.

Usage: python -m ingest.enrich_glossary"""
from __future__ import annotations

import html as htmllib
import re

import httpx
from psycopg.types.json import Jsonb  # noqa: F401  (kept for symmetry with other ingesters)

from app import db
from app.normalize import strip_tashkeel
from ingest.common import log

SEARCH = "https://islamic-content.com/search"
UA = {"User-Agent": "Mozilla/5.0 (compatible; Tahaqqaq/0.1)"}


def _text(fragment: str) -> str:
    t = re.sub(r"(?s)<script.*?</script>|<style.*?</style>", " ", fragment)
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", t))).strip()


def _title_key(t: str) -> str:
    """Compare titles with diacritics removed but hamza kept: «الأيمان» (oaths) must not match «الإيمان» (faith)."""
    t = strip_tashkeel(t).strip()
    return t[2:] if t.startswith("ال") else t


def definition_from(body: str) -> str:
    for marker in ("المادة الأساسية :", "التعريف اصطلاحًا", "التعريف اصطلاحا", "التعريف لغة", "مصطلحات ذات علاقة"):
        k = body.find(marker)
        if k >= 0:
            seg = body[k + len(marker) : k + len(marker) + 700]
            seg = re.split(r"قال الله تعالى|قال تعالى|﴿|انظر :|تعريفات أخرى", seg)[0]
            seg = seg.strip(" :")
            if len(seg) > 30:
                return seg[:450]
    return ""


def find_entry(c: httpx.Client, term: str) -> tuple[str, str] | None:
    """(url, definition) of the الجمهرة entry whose title is the term, or None."""
    links: list[str] = []
    for q in dict.fromkeys([term, term if term.startswith("ال") else "ال" + term]):
        page = c.get(SEARCH, params={"query": q}).text
        links += re.findall(r'href="(https://islamic-content\.com/t/\d+)"', page)
    links = list(dict.fromkeys(links))
    key = _title_key(term)
    for url in links[:25]:
        p = c.get(url).text
        title = re.search(r"<title>([^<]+)</title>", p)
        head = _title_key(_text(title.group(1)).split(" - ")[0]) if title else ""
        if head and head == key:
            definition = definition_from(_text(p))
            if definition:
                return url, definition
    return None


def run() -> None:
    with db.get_conn() as conn:
        terms = conn.execute("SELECT id, term_ar FROM glossary ORDER BY id").fetchall()
    found = 0
    with httpx.Client(timeout=25, follow_redirects=True, headers=UA) as c:
        for t in terms:
            try:
                hit = find_entry(c, t["term_ar"])
            except httpx.HTTPError as e:
                log(f"  {t['term_ar']}: unreachable ({e})")
                continue
            if not hit:
                log(f"  {t['term_ar']}: no entry found in الجمهرة — seed text kept")
                continue
            url, definition = hit
            with db.get_conn() as conn:
                conn.execute("UPDATE glossary SET source_url = %s, meaning_ar = %s WHERE id = %s", (url, definition, t["id"]))
            found += 1
            log(f"  {t['term_ar']}: {url}")
    log(f"[enrich_glossary] {found}/{len(terms)} terms linked to الجمهرة")


if __name__ == "__main__":
    run()
