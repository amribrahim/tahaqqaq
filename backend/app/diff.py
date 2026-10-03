"""Word-level diff tokens for the "مقارنة الصيغة" card.

Returns two token lists (input side, source side). Token kinds: 'eq' | 'del' | 'ins'.
Comparison is done on normalised words; the original words are displayed.
"""
from __future__ import annotations

import difflib
import re

from .normalize import normalize_arabic, normalize_latin

_SPLIT = re.compile(r"(\s+)")


def _words(text: str) -> list[str]:
    return [w for w in _SPLIT.split(text.strip()) if w != ""]


def diff_tokens(a: str, b: str, lang: str = "ar", trim: bool = True) -> tuple[list[dict], list[dict]]:
    """Diff `a` (input) against `b` (source). With `trim`, leading/trailing runs of source-only
    words are collapsed to an ellipsis when the source is much longer than the input, so a short
    quote from a long hadith is compared against the matching span only."""
    norm = normalize_arabic if lang == "ar" else normalize_latin
    aw, bw = _words(a), _words(b)
    ak = [norm(w) if w.strip() else " " for w in aw]
    bk = [norm(w) if w.strip() else " " for w in bw]
    sm = difflib.SequenceMatcher(a=ak, b=bk, autojunk=False)
    left: list[dict] = []
    right: list[dict] = []

    def push(side: list[dict], words: list[str], kind: str) -> None:
        for w in words:
            if not w.strip():
                side.append({"t": w, "k": "eq"})
            else:
                side.append({"t": w, "k": kind})

    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            push(left, aw[i1:i2], "eq")
            push(right, bw[j1:j2], "eq")
        elif op == "delete":
            push(left, aw[i1:i2], "del")
        elif op == "insert":
            push(right, bw[j1:j2], "ins")
        else:  # replace
            push(left, aw[i1:i2], "del")
            push(right, bw[j1:j2], "ins")
    right = _merge(right)
    left = _merge(left)
    if trim and len(bw) > 1.6 * len(aw) + 2:
        right = _trim_source(right)
    return left, right


def _trim_source(tokens: list[dict]) -> list[dict]:
    """Collapse leading/trailing 'ins' runs (source-only context) into an ellipsis."""
    first = next((i for i, t in enumerate(tokens) if t["k"] != "ins" and t["t"].strip()), None)
    last = next((i for i in range(len(tokens) - 1, -1, -1) if tokens[i]["k"] != "ins" and tokens[i]["t"].strip()), None)
    if first is None or last is None:
        return tokens
    core = tokens[first : last + 1]
    out: list[dict] = []
    if first > 0:
        out.append({"t": "… ", "k": "eq"})
    out.extend(core)
    if last < len(tokens) - 1:
        out.append({"t": " …", "k": "eq"})
    return out


def _merge(tokens: list[dict]) -> list[dict]:
    """Merge adjacent tokens of the same kind (whitespace joins its neighbours)."""
    out: list[dict] = []
    for t in tokens:
        if out and (out[-1]["k"] == t["k"] or (not t["t"].strip() and out[-1]["k"] != "eq" and False)):
            out[-1]["t"] += t["t"]
        else:
            out.append(dict(t))
    return out
