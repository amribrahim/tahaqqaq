"""Recompute matn_norm with normalize_ar for every stored record and re-embed the Arabic windows of
the records whose key changed. Usage: python -m ingest.renormalize"""
from __future__ import annotations

from app import db
from app.normalize import normalize_ar
from ingest.common import embed_chunks, log


def run() -> None:
    with db.get_conn() as conn:
        rows = conn.execute("SELECT id, matn_ar, matn_norm FROM texts ORDER BY id").fetchall()
    changed = [(r["id"], normalize_ar(r["matn_ar"])) for r in rows if normalize_ar(r["matn_ar"]) != r["matn_norm"]]
    log(f"[renormalize] {len(rows)} records, {len(changed)} keys changed")
    for i in range(0, len(changed), 2000):
        batch = changed[i : i + 2000]
        ids = [b[0] for b in batch]
        keys = [b[1] for b in batch]
        chunks = embed_chunks(keys, "ar")
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany("UPDATE texts SET matn_norm = %s WHERE id = %s", list(zip(keys, ids, strict=True)))
                cur.execute("DELETE FROM chunks WHERE lang = 'ar' AND text_id = ANY(%s)", (ids,))
                cur.executemany(
                    "INSERT INTO chunks (text_id, lang, pos, embedding) VALUES (%s, 'ar', %s, %s)",
                    [(tid, pos, v) for tid, ch in zip(ids, chunks, strict=True) for pos, v in enumerate(ch)],
                )
        log(f"  {min(i + 2000, len(changed))}/{len(changed)}")
    log("[renormalize] done")


if __name__ == "__main__":
    run()
