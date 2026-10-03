"""Experiment: embed the English windows with a candidate model into a side table (the live index is untouched),
so retrieval quality can be compared on the multilingual set. Usage:
    python -m eval.embed_candidate --model intfloat/multilingual-e5-large --table chunks_cand
e5 models expect "passage: " / "query: " prefixes; they are added automatically."""
from __future__ import annotations

import argparse
import time

import numpy as np
from fastembed import TextEmbedding

from app import db
from app.chunking import windows
from app.translation import english_key


def prefix(model: str, kind: str) -> str:
    return f"{kind}: " if "e5" in model else ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="intfloat/multilingual-e5-large")
    ap.add_argument("--table", default="chunks_cand")
    ap.add_argument("--path", default="", help="local folder with the model files (avoids cache symlink issues)")
    a = ap.parse_args()
    m = TextEmbedding(model_name=a.model, specific_model_path=a.path) if a.path else TextEmbedding(model_name=a.model)
    dim = len(next(iter(m.embed(["x"]))))
    with db.get_conn() as conn:
        conn.execute(f"DROP TABLE IF EXISTS {a.table}")
        conn.execute(f"CREATE TABLE {a.table} (text_id int, pos int, embedding vector({dim}))")
        rows = conn.execute("SELECT id, kind, text_en FROM texts WHERE text_en <> '' ORDER BY id").fetchall()
    print(f"{len(rows)} texts, dim {dim}", flush=True)
    t0 = time.time()
    for i in range(0, len(rows), 1000):
        batch = rows[i : i + 1000]
        flat, owners = [], []
        for r in batch:
            for pos, w in enumerate(windows(english_key(r["text_en"], r["kind"]), "en")):
                flat.append(prefix(a.model, "passage") + w)
                owners.append((r["id"], pos))
        vecs = np.array(list(m.embed(flat, batch_size=64)), dtype=np.float32)
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.executemany(f"INSERT INTO {a.table} (text_id, pos, embedding) VALUES (%s, %s, %s)",
                            [(tid, pos, v) for (tid, pos), v in zip(owners, vecs, strict=True)])
        done = min(i + 1000, len(rows))
        print(f"{done}/{len(rows)} texts · {time.time() - t0:.0f}s", flush=True)
    with db.get_conn() as conn:
        conn.execute(f"CREATE INDEX ON {a.table} USING hnsw (embedding vector_cosine_ops)")
    print("done", flush=True)


if __name__ == "__main__":
    main()
