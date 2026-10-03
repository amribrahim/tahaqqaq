"""Find the hadith/verse candidates inside a long text (article, OCR'd post, long paste).

Returns short spans most likely to be the quoted text, best first:
1. bracketed segments «…» "…" “…” (…) {…} with enough Arabic/Latin letters,
2. the span that follows an attribution marker (قال رسول الله ﷺ: …) up to the sentence end,
3. the longest sentence, as a fallback.
The pipeline verifies each candidate and keeps the one with the highest confidence."""
from __future__ import annotations

import re

_AR = re.compile(r"[؀-ۿ]")
_BRACKETS = re.compile(r"[«\"“({]\s*([^«»\"“”(){}]{12,400}?)\s*[»\"”)}]")
from .normalize import _tolerant  # noqa: E402  (diacritic-tolerant literal → regex)

_MARKER_AR = ["قال رسول الله", "قال النبي", "يقول النبي", "يقول رسول الله", "سمعت رسول الله", "سمعت النبي",
              "قوله", "عن النبي", "عن رسول الله", "قال عليه الصلاة والسلام"]
_MARKER = re.compile(
    "(?:" + "|".join(_tolerant(x) for x in _MARKER_AR)
    + r"|the prophet (?:muhammad )?(?:\(?pbuh\)?|ﷺ)?\s*said|messenger of allah said)"
    + r"[^:：\n]{0,60}?(?:" + _tolerant("صلى الله عليه وسلم") + r"|ﷺ|" + _tolerant("عليه الصلاة والسلام") + r")?"
    + r"\s*(?:" + _tolerant("يقول") + r"|" + _tolerant("قال") + r")?\s*[:：]?\s*",
    re.IGNORECASE,
)
_END = re.compile(r"(?:\s+رواه\s|\s+أخرجه\s|\s+متفق\s|[.؟!\n]|\s+\)\s|$)")
_NARRATION_TAIL = re.compile(r"\s*(?:رواه|أخرجه|متفق عليه|صححه)\b.*$")


def _ok(span: str) -> bool:
    letters = len(_AR.findall(span)) + len(re.findall(r"[A-Za-z]", span))
    return 12 <= len(span) <= 400 and letters >= 10


def _clean(span: str) -> str:
    span = _NARRATION_TAIL.sub("", span)
    return re.sub(r"\s+", " ", span).strip(" :،,.؛\"«»“”(){}")


def quote_candidates(text: str, limit: int = 8) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text)
    found: list[tuple[int, str]] = []  # (priority, span)
    for m in _BRACKETS.finditer(text):
        span = _clean(m.group(1))
        if _ok(span):
            # bracketed text right after an attribution marker is almost certainly the quote
            before = text[max(0, m.start() - 80) : m.start()]
            found.append((0 if _MARKER.search(before) else 1, span))
    for m in _MARKER.finditer(text):
        rest = text[m.end() : m.end() + 500]
        end = _END.search(rest)
        span = _clean(rest[: end.start()] if end and end.start() > 0 else rest[:300])
        if _ok(span):
            found.append((0, span))
    sents = [s.strip() for s in re.split(r"(?<=[.!؟?])\s+|\n+", text) if s.strip()]
    for s in sorted(sents, key=len, reverse=True):
        s = _clean(s)
        if _ok(s) and len(s.split()) > 6:
            found.append((2, s))
    out: list[str] = []
    seen: set[str] = set()
    for _, span in sorted(found, key=lambda x: x[0]):
        key = re.sub(r"\W+", "", span)[:60]
        if key in seen or any(key in re.sub(r"\W+", "", o) for o in out):
            continue
        seen.add(key)
        out.append(span)
        if len(out) >= limit:
            break
    return out
