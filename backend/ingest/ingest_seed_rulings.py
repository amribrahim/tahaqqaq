"""Ingest the curated rulings seed (famous circulated sayings outside the Six Books).

Usage: python -m ingest.ingest_seed_rulings
"""
from __future__ import annotations

import json
from pathlib import Path

from app.normalize import normalize_ar, normalize_latin
from app.translation import quoted_part
from ingest.common import dorar_url, embed_chunks, ensure_schema, log, upsert_records

SEED = Path(__file__).resolve().parent / "seeds" / "rulings_seed.json"


def load_rows() -> list[dict]:
    items = json.loads(SEED.read_text(encoding="utf-8"))["items"]
    rows = []
    for i, it in enumerate(items, 1):
        grades = []
        for g in it["grades"]:
            g = dict(g)
            g["url"] = g.get("url") or dorar_url(it["text_ar"])
            grades.append(g)
        g0 = grades[0]
        rows.append({
            "kind": "seed", "collection": "seed", "book_ar": g0["source_ar"], "book_en": g0["source_en"],
            "number": str(i), "chapter_ar": it.get("note_ar", ""), "chapter_en": it.get("note_en", ""),
            "text_ar": it["text_ar"], "matn_ar": it["text_ar"], "text_en": it.get("text_en", ""),
            "type_ar": it.get("type_ar", "حكمة منتشرة"), "type_en": it.get("type_en", "Popular saying"),
            "grades": grades, "source_url": dorar_url(it["text_ar"]), "alt_url": "",
            "meta": {"seed": True, "ruling_number": g0.get("number", "")},
        })
    return rows


def run() -> None:
    ensure_schema()
    rows = load_rows()
    log(f"[seed rulings] {len(rows)} items")
    ch_ar = embed_chunks([normalize_ar(r["matn_ar"]) for r in rows], "ar")
    ch_en = embed_chunks([normalize_latin(quoted_part(r["text_en"] or "")) for r in rows], "en")
    for i, r in enumerate(rows):
        r["chunks_ar"], r["chunks_en"] = ch_ar[i], ch_en[i]
    upsert_records(rows)


if __name__ == "__main__":
    run()
