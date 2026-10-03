"""Small deterministic classifiers that run BEFORE retrieval.

- is_generation_request : the user asks us to *write/invent* a hadith -> abstain, never call the LLM
- is_personal_fatwa     : a personal religious ruling question -> referral state
- looks_like_attribution: text framed as a hadith ("قال رسول الله", "the Prophet said")
"""
from __future__ import annotations

import re

from .normalize import normalize_arabic, normalize_latin

_GEN_AR = [
    r"\b(اكتب|أكتب|الف|ألف|اختلق|أنشئ|انشئ|ولد|صغ|ابتكر|اخترع|اصنع|أعطني|اعطني|هات)\b.*\b(حديث|احاديث|اية|ايات|اثر)\w*",
    r"\bحديث\w*\b.*\b(من عندك|من تاليفك|جديد|مخترع|مزيف)\b",
]
_GEN_EN = [
    r"\b(write|compose|invent|make up|create|generate|fabricate|produce|give me)\b.*\b(hadith|hadiths|ahadith|narration|verse|ayah)\b",
    r"\b(fake|fabricated|new|made[- ]up)\b.*\b(hadith|narration)\b",
]

_FATWA_AR = [
    r"\b(هل يجوز|هل يجوز لي|أيجوز|هل يحل|هل يحرم|هل يصح|هل علي|هل يلزمني|ما حكم|ما الحكم|ماحكم|أفتوني|افتوني|أريد فتوى|اريد فتوى|هل أنا|هل انا|هل زوجي|هل زوجتي|هل يحق لي|كيف أقضي|كيف اقضي|هل أقضي|هل تجب علي|هل يجب علي|هل يجب)\b",
    r"\b(زوجي|زوجتي|أبي|امي|أمي|أخي|اختي|أختي|ابني|ابنتي|مديري|جاري)\b.*\b(يجوز|حكم|حرام|حلال|اثم|إثم|ذنب|كفارة|طلاق|يمين)\b",
    r"\b(كفارة|كفارتي|نذرت|حلفت|طلقت|أفطرت|افطرت|نسيت|سهوت|جامعت)\b",
]
_FATWA_EN = [
    r"\b(is it (permissible|allowed|halal|haram|sinful|okay|ok)|can i|may i|am i allowed|do i have to|must i|what is the ruling|ruling on|is my|should i|is it a sin|what should i do|i broke my fast|i swore|i divorced|my husband|my wife|my father|my mother)\b",
]

_ATTRIB_AR = r"(قال رسول الله|قال النبي|عن النبي|قال صلى الله عليه وسلم|عن رسول الله|يقول النبي|حديث شريف|حديث قدسي|قال عليه الصلاة والسلام|ﷺ)"
_ATTRIB_EN = r"\b(the prophet (muhammad )?(said|says)|messenger of allah said|narrated|hadith|hadeeth|prophet ﷺ)\b"


def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def is_generation_request(text: str) -> bool:
    ar = normalize_arabic(text)
    en = normalize_latin(text)
    return _any(_GEN_AR, ar) or _any(_GEN_EN, en)


def is_personal_fatwa(text: str) -> bool:
    ar = normalize_arabic(text)
    en = normalize_latin(text)
    # A quoted hadith that merely contains "هل" is not a question; require question framing.
    return _any(_FATWA_AR, ar) or _any(_FATWA_EN, en)


def looks_like_attribution(text: str) -> bool:
    return bool(re.search(_ATTRIB_AR, text)) or bool(re.search(_ATTRIB_EN, normalize_latin(text)))


_SALAWAT = r"(?:صلى\s+(?:الله\s+)?عليه\s+(?:وآله\s+)?وسلم|صلي\s+(?:الله\s+)?عليه\s+وسلم|ﷺ|عليه الصلاة والسلام|عليه السلام)"
_ATTRIB_PREFIX = re.compile(
    r"^\s*(?:حديث شريف|حديث)?\s*[:：]?\s*"
    r"(?:عن\s+[^:：]{0,60}?(?:قال|قالت)\s*[:：]?\s*)?"          # عن أبي هريرة قال:
    r"(?:(?:قال|يقول|قالت)\s+)?"                                   # قال
    r"(?:رسول الله|النبي|الرسول|نبي الله|رسول الله ﷺ)?\s*"          # رسول الله
    rf"(?:{_SALAWAT})?\s*"                                         # ﷺ (OCR may drop «الله»)
    r"(?:قال|يقول|أنه قال)?\s*[:：]?\s*",
)


def strip_attribution(text: str) -> str:
    """Remove a leading attribution so that the matcher sees the saying itself."""
    t = _ATTRIB_PREFIX.sub("", text, count=1)
    t = re.sub(r"^\s*(?:the prophet(?: muhammad)?(?: \(?(?:pbuh|saw|peace be upon him)\)?| ﷺ)?\s*(?:said|says)\s*[:：]?\s*)", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^\s*(?:hadith|حديث شريف|حديث)\s*[:：]\s*", "", t, flags=re.IGNORECASE)
    # trailing narration note: رواه البخاري / متفق عليه
    t = re.sub(r"\s*(?:رواه|أخرجه|متفق عليه|صححه)\b.*$", "", t)
    return t.strip(' "«»“”\'')
