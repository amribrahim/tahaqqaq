"""Corpus-aware spelling correction for Arabic voice transcripts.

Speech-to-text makes spelling slips on classical Arabic: split or joined words («لولا» → «لو لا»), dropped endings
(«شفاعة» → «شفاع», «يصلي» → «يصل»), a missing initial alef («امرئ» → «مرئ», «ابن» → «بن»). When the transcript matches a
source text strongly, each mismatched stretch is compared with the source's words in a *spelling-blind* form: spaces,
hamza, a leading alef or «ال», and weak endings (ا ه ي ى) are ignored. Only when both forms are then identical is the
source's spelling used. Rules that keep it honest:
  - only Arabic, and only when the best match is strong (confidence ≥ SNAP_MIN_CONFIDENCE);
  - a different word is never changed: «بالنية» stays «بالنية» (a real narration), «الليف» is not turned into «الليث»;
  - words the speaker added are kept, words they left out are never inserted;
  - the original transcript is returned too and shown as "as heard"."""
from __future__ import annotations

import difflib
import re

from . import classify, matcher
from .normalize import normalize_ar, strip_tashkeel

SNAP_MIN_CONFIDENCE = 80


def skeleton(words: list[str]) -> str:
    """Spelling-blind form of a stretch of normalised words: no spaces, no hamza, no leading alef or «ال», no weak
    endings. Two stretches with the same skeleton differ only in how the transcriber spelled or spaced them."""
    out = []
    for w in words:
        w = w.replace("ء", "")
        w = re.sub(r"^ال(?=..)", "", w)
        w = re.sub(r"^ا(?=..)", "", w)
        w = re.sub(r"[اهيى]+$", "", w) or w
        out.append(w)
    return "".join(out)


def _display_words(text: str) -> list[str]:
    return re.sub(r"[^\w\s]", " ", strip_tashkeel(text)).split()


def snap(text: str) -> tuple[str, bool]:
    """(corrected text, whether anything changed)."""
    body = classify.strip_attribution(text) or text
    prefix = text[: len(text) - len(body)] if text.endswith(body) else ""
    found = matcher.search(body, lang="ar", kinds=None, limit=1)
    if not found or found[0]["confidence"] < SNAP_MIN_CONFIDENCE:
        return text, False
    rec = found[0]["record"]
    source = rec.matn_ar if rec.kind != "quran" else rec.text_ar
    hyp, ref = _display_words(body), _display_words(source)
    if not hyp or not ref:
        return text, False
    hn, rn = [normalize_ar(w) for w in hyp], [normalize_ar(w) for w in ref]
    out: list[str] = []
    changed = False
    for op, a1, a2, b1, b2 in difflib.SequenceMatcher(a=hn, b=rn, autojunk=False).get_opcodes():
        if op == "equal":
            out += hyp[a1:a2]
        elif op == "replace" and skeleton(hn[a1:a2]) == skeleton(rn[b1:b2]):
            out += ref[b1:b2]               # same word, the transcriber's spelling, spacing or ending slipped
            changed = True
        elif op in ("replace", "delete"):
            out += hyp[a1:a2]               # a different word, or words the speaker added: kept as heard
        # "insert": words of the source the speaker did not say are never added
    return (f"{prefix}{' '.join(out)}".strip(), True) if changed else (text, False)
