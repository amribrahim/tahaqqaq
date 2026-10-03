"""Seed the glossary table.

Primary source: ingest/seeds/glossary.csv (the 10 approved terms from the design handoff).
Optional: `--from-web` tries islamic-content.com/dictionary for extra terms; failures are non-fatal.

Usage: python -m ingest.ingest_glossary [--from-web]
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from psycopg.types.json import Jsonb

from app import db
from ingest.common import ensure_schema, log

SEED = Path(__file__).resolve().parent / "seeds" / "glossary.csv"


def load_seed() -> list[dict]:
    with SEED.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["avoid"] = [a.strip() for a in (r.get("avoid") or "").split(";") if a.strip()]
    return rows


def load_web() -> list[dict]:
    """Best-effort scrape of islamic-content.com/dictionary (structure may change)."""
    try:
        import httpx
        from bs4 import BeautifulSoup

        r = httpx.get("https://islamic-content.com/dictionary", timeout=30, follow_redirects=True)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        out = []
        for a in soup.select("a[href*='/dictionary/']")[:200]:
            term = a.get_text(strip=True)
            if term and any("؀" <= ch <= "ۿ" for ch in term):
                out.append({"term_ar": term, "term_en": "", "meaning_en": "", "meaning_ar": "", "avoid": [],
                            "note_ar": "", "note_en": "", "source_url": a["href"]})
        log(f"  fetched {len(out)} terms from islamic-content.com (names only; meanings need review)")
        return out
    except Exception as e:  # noqa: BLE001
        log(f"  islamic-content.com unavailable ({e}); using the seed only")
        return []


def run(from_web: bool) -> None:
    ensure_schema()
    rows = load_seed()
    if from_web:
        seen = {r["term_ar"] for r in rows}
        rows += [r for r in load_web() if r["term_ar"] not in seen and r["meaning_en"]]
    sql = """
    INSERT INTO glossary (term_ar, term_en, meaning_en, meaning_ar, avoid, note_ar, note_en, source_url)
    VALUES (%(term_ar)s, %(term_en)s, %(meaning_en)s, %(meaning_ar)s, %(avoid)s, %(note_ar)s, %(note_en)s, %(source_url)s)
    ON CONFLICT (term_ar) DO UPDATE SET term_en = EXCLUDED.term_en, meaning_en = EXCLUDED.meaning_en,
      meaning_ar = EXCLUDED.meaning_ar, avoid = EXCLUDED.avoid, note_ar = EXCLUDED.note_ar,
      note_en = EXCLUDED.note_en, source_url = EXCLUDED.source_url
    """
    with db.get_conn() as conn:
        for r in rows:
            conn.execute(sql, {**r, "avoid": Jsonb(r["avoid"])})
    log(f"[glossary] {len(rows)} terms upserted")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--from-web", action="store_true")
    run(p.parse_args().from_web)
