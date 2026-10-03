"""Short word windows for embedding.

The multilingual MiniLM model collapses long Arabic passages into near-identical vectors, but is
accurate on short spans. Every record is therefore embedded as overlapping windows of a few words
and the best window decides the record's semantic score."""
from __future__ import annotations

AR_WINDOW, AR_STRIDE, AR_MAX = 8, 5, 5
EN_WINDOW, EN_STRIDE, EN_MAX = 16, 10, 3


def windows(norm_text: str, lang: str = "ar") -> list[str]:
    size, stride, max_n = (EN_WINDOW, EN_STRIDE, EN_MAX) if lang == "en" else (AR_WINDOW, AR_STRIDE, AR_MAX)
    words = norm_text.split()
    if not words:
        return []
    if len(words) <= size:
        return [" ".join(words)]
    out = []
    for start in range(0, len(words), stride):
        out.append(" ".join(words[start : start + size]))
        if len(out) >= max_n or start + size >= len(words):
            break
    return out
