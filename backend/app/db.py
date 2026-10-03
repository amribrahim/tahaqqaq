"""Thin psycopg3 + pgvector access layer and schema bootstrap."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from .config import get_settings

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS texts (
  id            SERIAL PRIMARY KEY,
  kind          TEXT NOT NULL,                 -- hadith | quran | seed
  collection    TEXT NOT NULL,                 -- bukhari | muslim | abudawud | tirmidhi | nasai | ibnmajah | quran | seed
  book_ar       TEXT NOT NULL,
  book_en       TEXT NOT NULL,
  number        TEXT NOT NULL,                 -- hadith number, or "surah:ayah"
  chapter_ar    TEXT NOT NULL DEFAULT '',
  chapter_en    TEXT NOT NULL DEFAULT '',
  text_ar       TEXT NOT NULL,                 -- full text as displayed (with isnad for hadith)
  matn_ar       TEXT NOT NULL,                 -- the saying itself (what users quote)
  matn_norm     TEXT NOT NULL,                 -- normalised matching key
  text_en       TEXT NOT NULL DEFAULT '',      -- approved published translation
  text_en_norm  TEXT NOT NULL DEFAULT '',
  type_ar       TEXT NOT NULL DEFAULT 'حديث نبوي',
  type_en       TEXT NOT NULL DEFAULT 'Prophetic hadith',
  grades        JSONB NOT NULL DEFAULT '[]',   -- verbatim rulings from the source record
  source_url    TEXT NOT NULL,                 -- dorar.net / quran.com page
  alt_url       TEXT NOT NULL DEFAULT '',      -- sunnah.com page
  meta          JSONB NOT NULL DEFAULT '{}',
  UNIQUE (collection, number)
);

-- Short word-window embeddings (see app/chunking.py); several rows per text.
CREATE TABLE IF NOT EXISTS chunks (
  id        SERIAL PRIMARY KEY,
  text_id   INT NOT NULL REFERENCES texts(id) ON DELETE CASCADE,
  lang      TEXT NOT NULL,                     -- ar | en
  pos       INT NOT NULL,
  embedding vector({dim}) NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_ar_hnsw ON chunks USING hnsw (embedding vector_cosine_ops) WHERE lang = 'ar';
CREATE INDEX IF NOT EXISTS chunks_en_hnsw ON chunks USING hnsw (embedding vector_cosine_ops) WHERE lang = 'en';
CREATE INDEX IF NOT EXISTS chunks_text_idx ON chunks (text_id, lang);
CREATE INDEX IF NOT EXISTS texts_matn_trgm_idx ON texts USING gin (matn_norm gin_trgm_ops);
CREATE INDEX IF NOT EXISTS texts_en_trgm_idx ON texts USING gin (text_en_norm gin_trgm_ops);
CREATE INDEX IF NOT EXISTS texts_kind_idx ON texts (kind);

CREATE TABLE IF NOT EXISTS glossary (
  id         SERIAL PRIMARY KEY,
  term_ar    TEXT NOT NULL UNIQUE,
  term_en    TEXT NOT NULL,                     -- accepted transliteration
  meaning_en TEXT NOT NULL,
  meaning_ar TEXT NOT NULL,
  avoid      JSONB NOT NULL DEFAULT '[]',       -- literal renderings that distort the meaning
  note_ar    TEXT NOT NULL DEFAULT '',
  note_en    TEXT NOT NULL DEFAULT '',
  source_url TEXT NOT NULL DEFAULT ''
);

-- Texts fetched from the approved references (الدرر السنية: rulings, شروح, tafsir), keyed by the
-- matched source record's wording. Part of the retrieval corpus; never contains user input.
CREATE TABLE IF NOT EXISTS source_cache (
  key        TEXT PRIMARY KEY,
  source     TEXT NOT NULL,
  url        TEXT NOT NULL DEFAULT '',
  payload    JSONB NOT NULL DEFAULT '{}',
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ingest_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def connect() -> psycopg.Connection:
    conn = psycopg.connect(get_settings().database_url, row_factory=dict_row)
    # the extension must exist before the vector type can be registered on the connection
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.commit()
    register_vector(conn)
    return conn


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(dim: int) -> None:
    with get_conn() as conn:
        conn.execute(SCHEMA.replace("{dim}", str(dim)))
