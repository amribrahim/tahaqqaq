"""Translation-accuracy checks for non-Arabic input.

1. Glossary check: flags literal renderings that distort the meaning of approved terms and
   explains the term instead (data-driven from the `glossary` table, no LLM).
2. Approved-translation diff: word diff between the user's translation and the published one.
"""
from __future__ import annotations

import re

from .diff import diff_tokens
from .normalize import normalize_latin
from .records import GlossaryTerm


def glossary_notes(text: str, glossary: list[GlossaryTerm], lang: str = "ar") -> list[dict]:
    """Return notes for glossary terms that appear in the (Latin-script) text."""
    norm = " " + normalize_latin(text) + " "
    notes: list[dict] = []
    for g in glossary:
        term_hit = re.search(rf"\b{re.escape(g.term_en.lower())}\b", norm)
        wrong = [a for a in g.avoid if re.search(rf"\b{re.escape(a.lower())}\b", norm)]
        if not term_hit and not wrong:
            continue
        if wrong:
            sev = "high"
            text_ar = f"«{', '.join(wrong)}» ترجمة حرفية لمصطلح «{g.term_ar}» ({g.term_en}) تُغيّر معناه. " + (g.note_ar or "")
            text_en = f"'{', '.join(wrong)}' is a literal rendering of «{g.term_ar}» ({g.term_en}) that distorts it. " + (g.note_en or "")
        else:
            sev = "low"
            text_ar = f"«{g.term_ar}» ({g.term_en}) مصطلح شرعي يُنقل بلفظه ويُشرح: {g.meaning_ar}"
            text_en = f"«{g.term_ar}» ({g.term_en}) is a term of art: keep it and explain it. Meaning: {g.meaning_en}"
        notes.append({
            "severity": sev, "term_ar": g.term_ar, "term_en": g.term_en,
            "meaning_ar": g.meaning_ar, "meaning_en": g.meaning_en,
            "text_ar": text_ar.strip(), "text_en": text_en.strip(),
            "literal": wrong, "source_url": g.source_url,
        })
    notes.sort(key=lambda n: 0 if n["severity"] == "high" else 1)
    return notes


# Deterministic meaning rules for very common mistranslations of hadith wording.
_MEANING_RULES = [
    {
        "when_user": r"\b(is|are) (not )?(a )?muslims?\b", "when_source": r"\b(faith|believe|believer)\b",
        "ar": "ترجمة «لا يؤمن» بـ “is a Muslim” تنفي أصل الإسلام، والحديث ينفي كمال الإيمان لا أصله.",
        "en": "Rendering «لا يؤمن» as 'is a Muslim' denies Islam itself; the hadith negates the completeness of faith, not its existence.",
        "sev": "high",
    },
    {
        "when_user": r"\bholy war\b", "when_source": r"\b(jihad|striv)",
        "ar": "ترجمة «جهاد» بـ holy war غير دقيقة؛ تُنقل بلفظها Jihad مع بيان المعنى.",
        "en": "'Holy war' is not an accurate rendering of «جهاد»; keep 'Jihad' and explain it.",
        "sev": "high",
    },
]


def meaning_notes(user_text: str, approved_text: str) -> list[dict]:
    u, a = normalize_latin(user_text), normalize_latin(approved_text)
    out = []
    for r in _MEANING_RULES:
        if re.search(r["when_user"], u) and re.search(r["when_source"], a):
            out.append({"severity": r["sev"], "text_ar": r["ar"], "text_en": r["en"], "term_ar": "", "term_en": "",
                        "meaning_ar": "", "meaning_en": "", "literal": [], "source_url": ""})
    return out


# "…" / “…” anywhere; ‘…’ only when it opens after a colon or comma (‘ is also used as an ayn in
# transliterations such as ‘Umar, so a bare ‘ is not a quote mark)
_EN_QUOTED = re.compile(r'(?:[\"“«]|(?<=[:,])\s?‘)([^\"“”«»‘’]{12,})[\"”»’]')
_EN_SAID = re.compile(r"^.*\b(?:said|saying|says|say)\b\s*[:,]?\s*(?:that\s+)?", re.IGNORECASE | re.DOTALL)
_EN_NARRATED = re.compile(r"^.*?\bnarrated\b[^:]{0,80}:\s*", re.IGNORECASE | re.DOTALL)


def quoted_part(text_en: str, depth: int = 0) -> str:
    """The published translations start with a narrator preamble; keep the Prophet's words.
    Applied recursively because a Companion's quoted report often quotes the Prophet inside it."""
    quotes = [q.strip() for q in _EN_QUOTED.findall(text_en)]
    if quotes and sum(len(q) for q in quotes) >= 0.2 * len(text_en):
        inner = " ".join(quotes)
        return quoted_part(inner, depth + 1) if depth < 2 else inner
    for rx in (_EN_SAID, _EN_NARRATED):
        m = rx.match(text_en)
        if m and len(text_en) - m.end() >= 15 and m.end() < 0.6 * len(text_en):
            rest = text_en[m.end():].strip(' "“”‘’\'')
            return quoted_part(rest, depth + 1) if depth < 2 else rest
    return text_en.strip(' "“”‘’\'')


def translation_card(user_text: str, record, glossary: list[GlossaryTerm]) -> dict | None:
    """Build the translation-accuracy card for an English input matched to `record`."""
    approved = quoted_part(record.text_en or "")
    if not approved:
        return None
    user_tok, appr_tok = diff_tokens(user_text, approved, lang="en")
    issues = meaning_notes(user_text, approved)
    flagged = {w for i in issues for w in re.findall(r"[a-z ]+", i["text_en"].lower())}
    for n in glossary_notes(user_text, glossary):
        if n["severity"] == "high" and not any(lit in " ".join(flagged) for lit in n["literal"]):
            issues.append(n)
    changed = any(t["k"] != "eq" for t in user_tok) or any(t["k"] != "eq" for t in appr_tok)
    return {
        "original_ar": record.matn_ar,
        "user_tokens": user_tok,
        "approved_tokens": appr_tok,
        "approved_text": approved,
        "needs_fix": bool(issues) or changed,
        "issues": issues,
    }


def english_key(text_en: str, kind: str) -> str:
    """English matching key: for a verse the whole translation minus bracketed insertions
    (Hilali-Khan adds «(O Muhammad ﷺ)» etc.), for a hadith only the Prophet's words."""
    if kind == "quran":
        t = re.sub(r"^\s*\d+\.\s*", "", text_en or "")
        t = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", t)
        return normalize_latin(t)
    return normalize_latin(quoted_part(text_en or ""))
