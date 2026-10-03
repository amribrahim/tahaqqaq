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


# Formulas and references that often sit in brackets next to a quote but are never the quote itself:
# honorifics («صلى الله عليه وسلم», "(peace be upon him)") and source notes ("(Sahih al-Bukhari 1)", «رواه مسلم»).
_FORMULAS = [
    "صلى الله عليه وسلم", "صلى الله عليه وآله وسلم", "عليه الصلاة والسلام", "عليه السلام", "عليهم السلام",
    "رضي الله عنه", "رضي الله عنها", "رضي الله عنهما", "رضي الله عنهم", "رحمه الله", "رحمهم الله",
    "سبحانه وتعالى", "تبارك وتعالى", "عز وجل", "جل جلاله", "تعالى",
]
_FORMULA_RE = re.compile("|".join(_tolerant(x) for x in _FORMULAS))
_FORMULA_EN = re.compile(
    r"\b(?:peace(?: and blessings)? (?:of allah )?be upon (?:him|her|them)|upon him be peace|pbuh|p\.b\.u\.h|saws?|s\.a\.w|swt"
    r"|sallall?ahu? (?:'?alayhi|alaihi) wa ?sall?am|alayhis? salam|may allah (?:bless him and grant him peace|be pleased with (?:him|her|them|both of them)"
    r"|have mercy (?:on|upon) (?:him|her|them))|radiy?all?ahu? '?anh(?:u|a|uma|um)|rahimahull?ah|subhanahu wa ta'?ala|glorified and exalted be he"
    r"|the exalted|azza wa jall?a)\b", re.IGNORECASE)
_REFERENCE = re.compile(
    r"\b(?:sahih|sunan|jami'?|musnad|al|bukhari|muslim|abu dawud|abi dawud|dawud|tirmidhi|nasa'?i|ibn majah|majah|ahmad|malik|muwatta"
    r"|narrated|reported|recorded|by|in|hadith|no|number|book|vol|volume|and|graded|authentic|agreed upon)\b|\d+", re.IGNORECASE)
_AR_LETTER = "\u0621-\u064A\u0671-\u06D3"
_REFERENCE_AR = re.compile(
    rf"(?<![{_AR_LETTER}])(?:[وف])?(?:" + "|".join(_tolerant(x) for x in [
        "رواه", "أخرجه", "متفق عليه", "صححه", "حسنه", "صحيح البخاري", "صحيح مسلم", "البخاري", "مسلم", "سنن", "أبو داود",
        "أبي داود", "الترمذي", "النسائي", "ابن ماجه", "أحمد", "مالك", "الموطأ", "حديث", "رقم", "الألباني"])
    + rf")(?![{_AR_LETTER}])|[0-9٠-٩]+")


def substantive(span: str) -> bool:
    """True when the span says something of its own once honorifics and source references are removed
    (at least three words left), so that «(صلى الله عليه وسلم)» or "(Sahih Muslim 55)" is never taken as the quote."""
    rest = _FORMULA_RE.sub(" ", span)
    rest = _FORMULA_EN.sub(" ", rest)
    rest = _REFERENCE_AR.sub(" ", rest)
    rest = _REFERENCE.sub(" ", rest)
    words = [w for w in re.findall(r"[^\W\d_]+", rest) if len(w) > 1]
    return len(words) >= 3


def _ok(span: str) -> bool:
    letters = len(_AR.findall(span)) + len(re.findall(r"[A-Za-z]", span))
    return 12 <= len(span) <= 400 and letters >= 10 and substantive(span)


def _clean(span: str) -> str:
    span = _NARRATION_TAIL.sub("", span)
    return re.sub(r"\s+", " ", span).strip(" :،,.؛\"«»“”(){}")


def is_marked(text: str, span: str) -> bool:
    """The span is presented as a quotation: inside quote marks, or right after an attribution («قال رسول الله ﷺ», "the Prophet said")."""
    i = text.find(span)
    if i < 0:
        return False
    before, after = text[max(0, i - 80) : i], text[i + len(span) : i + len(span) + 3]
    quoted = bool(re.search(r"[«\"“]\s*$", before)) and bool(re.match(r"\s*[»\"”]", after))
    arabic_paren = bool(_AR.search(span)) and bool(re.search(r"\(\s*$", before))
    return quoted or arabic_paren or bool(_MARKER.search(before))


def quote_candidates(text: str, limit: int = 8) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text)
    found: list[tuple[int, str]] = []  # (priority, span)
    for m in _BRACKETS.finditer(text):
        span = _clean(m.group(1))
        if m.group(0)[0] in "({" and not _AR.search(span):
            continue  # in English, parentheses hold asides ("(peace be upon him)", "(i.e. ...)"), not quotations
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
