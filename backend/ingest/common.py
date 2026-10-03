"""Shared helpers for the ingestion scripts."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import httpx
import numpy as np

from app import db
from app.embeddings import get_embedder
from app.normalize import normalize_ar, strip_tashkeel
from app.translation import english_key

DATA_DIR = Path(os.environ.get("TAHQAQ_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

CDN = "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def fetch_json(url: str, cache_name: str) -> dict:
    path = DATA_DIR / cache_name
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    log(f"  downloading {url}")
    with httpx.Client(timeout=120, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        path.write_text(r.text, encoding="utf-8")
        return r.json()


def dorar_url(matn: str, words: int = 6) -> str:
    """dorar.net has no stable per-hadith id in open datasets; deep-link into its search.
    The query keeps the original spelling (hamza, ta-marbuta) with diacritics and punctuation
    removed, because dorar's search matches the printed wording."""
    import re

    plain = re.sub(r"[^\w\s]", " ", strip_tashkeel(matn))
    q = " ".join(plain.split()[:words])
    return f"https://dorar.net/hadith/search?q={quote(q)}"


def ensure_schema() -> int:
    emb = get_embedder()
    db.init_schema(emb.dim)
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO ingest_meta (key, value) VALUES ('embedder', %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (emb.name,),
        )
    return emb.dim


def embed_chunks(norm_texts: list[str], lang: str) -> list[list[np.ndarray]]:
    """Embed the word windows of every text; returns one list of vectors per text."""
    from app.chunking import windows

    flat, spans = [], []
    for t in norm_texts:
        w = windows(t, lang)
        spans.append((len(flat), len(w)))
        flat.extend(w)
    vecs = embed_texts(flat)
    return [[vecs[a + k] for k in range(n)] for a, n in spans]


def embed_texts(texts: list[str]) -> np.ndarray:
    emb = get_embedder()
    out = []
    for i in range(0, len(texts), 512):
        out.append(emb.embed(texts[i : i + 512]))
        log(f"    embedded {min(i + 512, len(texts))}/{len(texts)}")
    return np.vstack(out) if out else np.zeros((0, emb.dim), dtype=np.float32)


def upsert_records(rows: list[dict]) -> int:
    """rows: dicts with the `texts` columns plus `chunks_ar` / `chunks_en` (lists of vectors)."""
    if not rows:
        return 0
    sql = """
    INSERT INTO texts (kind, collection, book_ar, book_en, number, chapter_ar, chapter_en, text_ar, matn_ar,
                       matn_norm, text_en, text_en_norm, type_ar, type_en, grades, source_url, alt_url, meta)
    VALUES (%(kind)s, %(collection)s, %(book_ar)s, %(book_en)s, %(number)s, %(chapter_ar)s, %(chapter_en)s,
            %(text_ar)s, %(matn_ar)s, %(matn_norm)s, %(text_en)s, %(text_en_norm)s, %(type_ar)s, %(type_en)s,
            %(grades)s, %(source_url)s, %(alt_url)s, %(meta)s)
    ON CONFLICT (collection, number) DO UPDATE SET
      book_ar = EXCLUDED.book_ar, book_en = EXCLUDED.book_en, chapter_ar = EXCLUDED.chapter_ar,
      chapter_en = EXCLUDED.chapter_en, text_ar = EXCLUDED.text_ar, matn_ar = EXCLUDED.matn_ar,
      matn_norm = EXCLUDED.matn_norm, text_en = EXCLUDED.text_en, text_en_norm = EXCLUDED.text_en_norm,
      type_ar = EXCLUDED.type_ar, type_en = EXCLUDED.type_en, grades = EXCLUDED.grades,
      source_url = EXCLUDED.source_url, alt_url = EXCLUDED.alt_url, meta = EXCLUDED.meta
    RETURNING id
    """
    from psycopg.types.json import Jsonb

    n = 0
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            for i in range(0, len(rows), 500):
                batch = []
                for r in rows[i : i + 500]:
                    r = dict(r)
                    r["grades"] = Jsonb(r.get("grades") or [])
                    r["meta"] = Jsonb(r.get("meta") or {})
                    r.setdefault("alt_url", "")
                    r.setdefault("text_en", "")
                    r["text_en_norm"] = english_key(r.get("text_en") or "", r.get("kind", "hadith"))
                    r["matn_norm"] = normalize_ar(r["matn_ar"])
                    batch.append(r)
                ids = []
                for r in batch:
                    ids.append(cur.execute(sql, r).fetchone()["id"])
                cur.execute("DELETE FROM chunks WHERE text_id = ANY(%s)", (ids,))
                chunk_rows = []
                for tid, r in zip(ids, batch, strict=True):
                    for lang in ("ar", "en"):
                        for pos, v in enumerate(r.get(f"chunks_{lang}") or []):
                            chunk_rows.append((tid, lang, pos, v))
                cur.executemany("INSERT INTO chunks (text_id, lang, pos, embedding) VALUES (%s, %s, %s, %s)", chunk_rows)
                n += len(batch)
                log(f"    upserted {n}/{len(rows)}")
    return n
