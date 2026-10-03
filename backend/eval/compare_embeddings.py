"""Compare the live embedding model with a candidate on retrieval alone (recall@k of the labelled record) using the
English side of the multilingual benchmark (machine translations of the inputs, and the English inputs as typed).
Usage: python -m eval.compare_embeddings --rows rows.json --cand-path ~/.cache/e5-large [--cand-table chunks_cand]"""
from __future__ import annotations

import argparse
import json

import numpy as np
from fastembed import TextEmbedding

from app import db
from app.normalize import normalize_latin

LIVE = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
CAND = "intfloat/multilingual-e5-large"


def top_ids(conn, table: str, vec: np.ndarray, k: int, lang_filter: bool) -> list[int]:
    where = "WHERE lang = 'en'" if lang_filter else ""
    rows = conn.execute(
        f"WITH nn AS (SELECT text_id, 1 - (embedding <=> %(v)s) AS s FROM {table} {where} ORDER BY embedding <=> %(v)s LIMIT 200) "
        "SELECT text_id, max(s) AS s FROM nn GROUP BY text_id ORDER BY s DESC LIMIT %(k)s", {"v": vec, "k": k}).fetchall()
    return [r["text_id"] for r in rows]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True, help="saved rows from eval.run_multilingual --save")
    ap.add_argument("--cand-path", default="")
    ap.add_argument("--cand-table", default="chunks_cand")
    a = ap.parse_args()
    rows = json.load(open(a.rows, encoding="utf-8"))
    live = TextEmbedding(model_name=LIVE)
    cand = TextEmbedding(model_name=CAND, specific_model_path=a.cand_path) if a.cand_path else TextEmbedding(model_name=CAND)
    hits = {"live": {1: 0, 5: 0, 10: 0}, "cand": {1: 0, 5: 0, 10: 0}}
    n = 0
    with db.get_conn() as conn:
        for r in rows:
            q = normalize_latin(r.get("mt") or r["text"]) if (r.get("mt") or r["lang"] == "en") else ""
            if not q:
                continue
            c, num = r["expect_record"][0]
            row = conn.execute("SELECT id FROM texts WHERE collection = %s AND number = %s", (c, num)).fetchone()
            if not row:
                continue
            n += 1
            vl = np.array(next(iter(live.embed([" ".join(q.split()[:40])]))), dtype=np.float32)
            vc = np.array(next(iter(cand.embed(["query: " + q]))), dtype=np.float32)
            vl /= np.linalg.norm(vl)
            vc /= np.linalg.norm(vc)
            for name, ids in (("live", top_ids(conn, "chunks", vl, 10, True)), ("cand", top_ids(conn, a.cand_table, vc, 10, False))):
                for k in (1, 5, 10):
                    hits[name][k] += row["id"] in ids[:k]
    print(f"{n} English queries")
    print("| Model | recall@1 | recall@5 | recall@10 |\n|---|---|---|---|")
    for name, label in (("live", LIVE), ("cand", CAND)):
        h = hits[name]
        print(f"| {label} | {h[1] / n:.0%} | {h[5] / n:.0%} | {h[10] / n:.0%} |")


if __name__ == "__main__":
    main()
