"""Recompute the English matching key and English embeddings only (fast re-index after a change
to how the English translation is prepared). Usage: python -m ingest.reembed_en"""
from __future__ import annotations

from app import db
from app.translation import english_key
from ingest.common import embed_chunks, log


def run() -> None:
    with db.get_conn() as conn:
        rows = conn.execute("SELECT id, kind, text_en FROM texts WHERE text_en <> '' ORDER BY id").fetchall()
    log(f"[reembed_en] {len(rows)} texts")
    for i in range(0, len(rows), 2000):
        batch = rows[i : i + 2000]
        keys = [english_key(r["text_en"], r["kind"]) for r in batch]
        chunks = embed_chunks(keys, "en")
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                ids = [r["id"] for r in batch]
                cur.execute("DELETE FROM chunks WHERE lang = 'en' AND text_id = ANY(%s)", (ids,))
                cur.executemany("UPDATE texts SET text_en_norm = %s WHERE id = %s", list(zip(keys, ids, strict=True)))
                cur.executemany(
                    "INSERT INTO chunks (text_id, lang, pos, embedding) VALUES (%s, 'en', %s, %s)",
                    [(tid, pos, v) for tid, ch in zip(ids, chunks, strict=True) for pos, v in enumerate(ch)],
                )
        log(f"  {min(i + 2000, len(rows))}/{len(rows)}")
    log("[reembed_en] done")


if __name__ == "__main__":
    run()
