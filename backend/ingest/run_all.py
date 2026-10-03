"""Run every ingestion step: python -m ingest.run_all [--limit N] [--books ...]"""
from __future__ import annotations

import argparse

from ingest import (
    enrich_glossary,
    ingest_glossary,
    ingest_hadith,
    ingest_quran,
    ingest_seed_rulings,
    quran_kfgqpc,
)
from ingest.common import log

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None, help="per-book hadith cap (dev only)")
    p.add_argument("--books", default=",".join(ingest_hadith.DEFAULT_BOOKS))
    p.add_argument("--skip-quran", action="store_true")
    a = p.parse_args()
    ingest_glossary.run(from_web=False)
    ingest_seed_rulings.run()
    if not a.skip_quran:
        ingest_quran.run()
        quran_kfgqpc.run()
    ingest_hadith.run([b for b in a.books.split(",") if b], a.limit)
    enrich_glossary.run()
    log("[done] ingestion complete")
