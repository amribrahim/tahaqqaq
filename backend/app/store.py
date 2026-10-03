"""Vector + lexical retrieval over the `texts` table.

Two implementations share one interface:
- PgStore     : pgvector cosine search + pg_trgm word_similarity (production, docker-compose)
- MemoryStore : numpy + rapidfuzz, used by the test-suite and by `EMBEDDER=hash` smoke runs
"""
from __future__ import annotations

from functools import lru_cache
from typing import Protocol

import numpy as np
from rapidfuzz import fuzz

from .config import get_settings
from .records import GlossaryTerm, Record


class Store(Protocol):
    def get_record(self, collection: str, number: str) -> Record | None: ...
    def exact_search(self, norm_query: str, lang: str, kinds: list[str] | None, limit: int) -> list[Record]: ...
    def vector_search(self, vec: np.ndarray, lang: str, kinds: list[str] | None, limit: int) -> list[Record]: ...
    def lexical_search(self, norm_query: str, lang: str, kinds: list[str] | None, limit: int) -> list[Record]: ...
    def glossary(self) -> list[GlossaryTerm]: ...
    def counts(self) -> dict[str, int]: ...


class PgStore:
    def __init__(self) -> None:
        from . import db

        self._db = db

    def get_record(self, collection, number):
        with self._db.get_conn() as conn:
            row = conn.execute("SELECT * FROM texts WHERE collection = %s AND number = %s", (collection, number)).fetchone()
        return Record.from_row(row) if row else None

    def exact_search(self, norm_query, lang, kinds, limit):
        """Stage 1 of the cascade: the key equals, or is contained in, a record key."""
        col = "text_en_norm" if lang == "en" else "matn_norm"
        where = f"({col} = %(q)s OR (char_length(%(q)s) >= 15 AND position(%(q)s in {col}) > 0))"
        if kinds:
            where += " AND kind = ANY(%(kinds)s)"
        sql = f"SELECT * FROM texts WHERE {where} ORDER BY ({col} = %(q)s) DESC, char_length({col}) LIMIT %(limit)s"
        with self._db.get_conn() as conn:
            rows = conn.execute(sql, {"q": norm_query, "kinds": kinds, "limit": limit}).fetchall()
        out = []
        for r in rows:
            rec = Record.from_row(r)
            rec.lexical, rec.stage = 1.0, "exact"
            out.append(rec)
        return out

    def vector_search(self, vec, lang, kinds, limit):
        kind_where = "WHERE t.kind = ANY(%(kinds)s)" if kinds else ""
        sql = f"""
            WITH nn AS (
              SELECT text_id, 1 - (embedding <=> %(vec)s) AS semantic
              FROM chunks WHERE lang = %(lang)s
              ORDER BY embedding <=> %(vec)s LIMIT 120
            )
            SELECT t.*, max(nn.semantic) AS semantic
            FROM nn JOIN texts t ON t.id = nn.text_id {kind_where}
            GROUP BY t.id ORDER BY semantic DESC LIMIT %(limit)s
        """
        with self._db.get_conn() as conn:
            rows = conn.execute(sql, {"vec": vec, "lang": lang, "kinds": kinds, "limit": limit}).fetchall()
        return [Record.from_row(r) for r in rows]

    def lexical_search(self, norm_query, lang, kinds, limit):
        col = "text_en_norm" if lang == "en" else "matn_norm"
        where = f"{col} <> ''" + (" AND kind = ANY(%(kinds)s)" if kinds else "")
        # word_similarity(q, doc) is high when q matches a substring of doc: good for partial quotes.
        # The trigram probe uses the first words only; the full-text rescoring happens in matcher.py.
        q = " ".join(norm_query.split()[:12])
        sql = f"""
            SELECT *, word_similarity(%(q)s, {col}) AS lexical
            FROM texts WHERE {where} AND %(q)s <%% {col}
            ORDER BY lexical DESC LIMIT %(limit)s
        """
        with self._db.get_conn() as conn:
            conn.execute("SET pg_trgm.word_similarity_threshold = 0.35")
            rows = conn.execute(sql, {"q": q, "kinds": kinds, "limit": limit}).fetchall()
        return [Record.from_row(r) for r in rows]

    def glossary(self):
        with self._db.get_conn() as conn:
            rows = conn.execute("SELECT * FROM glossary ORDER BY id").fetchall()
        return [GlossaryTerm(**{k: r[k] for k in GlossaryTerm.__dataclass_fields__}) for r in rows]

    def counts(self):
        with self._db.get_conn() as conn:
            rows = conn.execute("SELECT kind, count(*) AS n FROM texts GROUP BY kind").fetchall()
            g = conn.execute("SELECT count(*) AS n FROM glossary").fetchone()
        out = {r["kind"]: int(r["n"]) for r in rows}
        out["glossary"] = int(g["n"]) if g else 0
        return out


class MemoryStore:
    """records + per-language chunk matrices. `owner_*[j]` is the record index of chunk row j."""

    def __init__(self, records: list[Record], glossary: list[GlossaryTerm],
                 chunks_ar: np.ndarray, owner_ar: np.ndarray, chunks_en: np.ndarray, owner_en: np.ndarray) -> None:
        self.records = records
        self._glossary = glossary
        self._chunks = {"ar": (chunks_ar, owner_ar), "en": (chunks_en, owner_en)}

    @classmethod
    def build(cls, records: list[Record], glossary: list[GlossaryTerm], embedder) -> MemoryStore:
        from .chunking import windows

        mats, owners = {}, {}
        for lang in ("ar", "en"):
            texts, own = [], []
            for i, r in enumerate(records):
                for w in windows(r.text_en_norm if lang == "en" else r.matn_norm, lang):
                    texts.append(w)
                    own.append(i)
            mats[lang] = embedder.embed(texts) if texts else np.zeros((0, embedder.dim), dtype=np.float32)
            owners[lang] = np.array(own, dtype=np.int64)
        return cls(records, glossary, mats["ar"], owners["ar"], mats["en"], owners["en"])

    def _filter(self, kinds):
        return [i for i, r in enumerate(self.records) if not kinds or r.kind in kinds]

    def get_record(self, collection, number):
        return next((r for r in self.records if r.collection == collection and r.number == number), None)

    def exact_search(self, norm_query, lang, kinds, limit):
        out = []
        for i in self._filter(kinds):
            r = self.records[i]
            doc = r.text_en_norm if lang == "en" else r.matn_norm
            if doc and (doc == norm_query or (len(norm_query) >= 15 and norm_query in doc)):
                rr = Record(**{**r.__dict__})
                rr.lexical, rr.stage = 1.0, "exact"
                out.append(rr)
        out.sort(key=lambda r: (0 if (r.text_en_norm if lang == "en" else r.matn_norm) == norm_query else 1, len(r.matn_norm)))
        return out[:limit]

    def vector_search(self, vec, lang, kinds, limit):
        mat, owner = self._chunks[lang]
        if mat.shape[0] == 0:
            return []
        allowed = set(self._filter(kinds))
        sims = mat @ vec
        best: dict[int, float] = {}
        for j in np.argsort(-sims):
            i = int(owner[j])
            if i in allowed and i not in best:
                best[i] = float(sims[j])
                if len(best) >= limit:
                    break
        out = []
        for i, s in best.items():
            r = Record(**self.records[i].__dict__)
            r.semantic = s
            out.append(r)
        return out

    def lexical_search(self, norm_query, lang, kinds, limit):
        scored = []
        for i in self._filter(kinds):
            r = self.records[i]
            doc = r.text_en_norm if lang == "en" else r.matn_norm
            if not doc:
                continue
            s = fuzz.partial_ratio(norm_query, doc) / 100.0
            if s >= 0.25:
                rr = Record(**r.__dict__)
                rr.lexical = s
                scored.append(rr)
        scored.sort(key=lambda r: -r.lexical)
        return scored[:limit]

    def glossary(self):
        return list(self._glossary)

    def counts(self):
        out: dict[str, int] = {}
        for r in self.records:
            out[r.kind] = out.get(r.kind, 0) + 1
        out["glossary"] = len(self._glossary)
        return out


_override: Store | None = None


def set_store(store: Store | None) -> None:
    """Tests inject a MemoryStore here."""
    global _override
    _override = store
    get_store.cache_clear()


@lru_cache
def get_store() -> Store:
    if _override is not None:
        return _override
    get_settings()
    return PgStore()
