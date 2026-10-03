"""Pluggable embedding backends.

- LocalEmbedder : fastembed ONNX model (multilingual MiniLM, 384 dims). Used by docker-compose & tests.
- OpenAIEmbedder: text-embedding-3-small (1536 dims) for hosts with little RAM (Render free tier).
- HashEmbedder  : deterministic char n-gram hashing. No semantics; only for fast unit tests.

All backends return L2-normalised vectors so cosine == dot product.
Always embed the NORMALISED text (matn_norm / text_en_norm): diacritics badly distort MiniLM similarity.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Protocol

import numpy as np

from .config import get_settings


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


def _l2(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return v / n


class LocalEmbedder:
    def __init__(self, model: str) -> None:
        import os

        from fastembed import TextEmbedding  # lazy import (heavy)

        self.name = f"local:{model}"
        cache_dir = os.environ.get("FASTEMBED_CACHE_PATH") or os.path.expanduser("~/.cache/fastembed")
        self._model = TextEmbedding(model_name=model, cache_dir=cache_dir)
        self.dim = int(next(iter(self._model.embed(["x"]))).shape[0])

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vecs = np.array(list(self._model.embed(texts, batch_size=64)), dtype=np.float32)
        return _l2(vecs)


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str) -> None:
        import httpx

        self.name = f"openai:{model}"
        self._client = httpx.Client(
            base_url="https://api.openai.com/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60,
        )
        self._model = model
        self.dim = 1536 if "small" in model else 3072

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        out: list[list[float]] = []
        for i in range(0, len(texts), 256):
            batch = texts[i : i + 256]
            r = self._client.post("/embeddings", json={"model": self._model, "input": batch})
            r.raise_for_status()
            data = sorted(r.json()["data"], key=lambda d: d["index"])
            out.extend(d["embedding"] for d in data)
        return _l2(np.array(out, dtype=np.float32))


class HashEmbedder:
    """Char-trigram hashing into 384 dims. Deterministic, offline, no semantics."""

    name = "hash"
    dim = 384

    def embed(self, texts: list[str]) -> np.ndarray:
        vecs = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, t in enumerate(texts):
            t = f"  {t}  "
            for i in range(len(t) - 2):
                h = int(hashlib.blake2b(t[i : i + 3].encode(), digest_size=4).hexdigest(), 16)
                vecs[row, h % self.dim] += 1.0
        return _l2(vecs)


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    if s.embedder == "openai":
        if not s.openai_api_key:
            raise RuntimeError("EMBEDDER=openai requires OPENAI_API_KEY")
        return OpenAIEmbedder(s.openai_api_key, s.openai_embed_model)
    if s.embedder == "hash":
        return HashEmbedder()
    return LocalEmbedder(s.embed_model)
