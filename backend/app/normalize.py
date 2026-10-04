"""Arabic normalisation used for matching.

The displayed text is never normalised; only the matching key is.
Steps: strip tashkeel/tatweel, unify alef/ya/ta-marbuta forms, drop punctuation,
convert Arabic-Indic digits, collapse whitespace.
"""
from __future__ import annotations

import re
import unicodedata

_TASHKEEL = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_ALEF = re.compile(r"[آأإٱٲٳٵ]")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_ARABIC_LETTERS = re.compile(r"[؀-ۿ]")
_LATIN_LETTERS = re.compile(r"[A-Za-z]")

# Uthmani-script specific marks (small alef, sukun variants, etc.) that are not in the
# generic tashkeel range above.
_UTHMANI = re.compile(r"[ۖ-ۜ۟-۪ۨ-ۭٖ-ٰٟ࣓-ࣿ]")


def strip_tashkeel(text: str) -> str:
    text = _UTHMANI.sub("", text)
    return _TASHKEEL.sub("", text)


def normalize_arabic(text: str) -> str:
    """Return a normalised matching key for Arabic (safe for mixed text)."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = strip_tashkeel(text)
    text = _ALEF.sub("ا", text)  # آ أ إ ٱ -> ا
    text = text.replace("ى", "ي")  # ى -> ي
    text = text.replace("ة", "ه")  # ة -> ه
    text = text.replace("ؤ", "و")  # ؤ -> و
    text = text.replace("ئ", "ي")  # ئ -> ي
    text = text.replace("ک", "ك").replace("ی", "ي")  # Persian kaf/ya
    text = text.translate(_AR_DIGITS)
    text = _PUNCT.sub(" ", text)
    text = _WS.sub(" ", text).strip()
    return text.lower()


def normalize_latin(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[’‘`´]", "'", text)
    text = re.sub(r"[^a-z0-9'\s]", " ", text)
    return _WS.sub(" ", text).strip()


def detect_language(text: str) -> str:
    """Very small heuristic: 'ar' if Arabic letters dominate, else 'en' (any Latin script)."""
    ar = len(_ARABIC_LETTERS.findall(text))
    la = len(_LATIN_LETTERS.findall(text))
    if ar == 0 and la == 0:
        return "ar"
    # Arabic is the primary language: a mixed paste (hadith + its translation) is treated as Arabic
    return "ar" if ar >= 0.6 * la else "en"


_URDU_PERSIAN_LETTERS = re.compile(r"[پچژگٹڈڑںےۓہۀۂ\u200c]")  # never in Arabic text (ی ک ھ are mere spelling variants)
# Persian function words that are not Arabic words, so Arabic typed with Persian letters (فی، لکل) stays Arabic
_PERSIAN_WORDS = set("را است که از برای های می نیست هست دارد دارند کند کنند شود شده بود یک آن تا اگر".split())
_EN_STOP = set("the of and to in is was that he for it with as his on be at by i this had not are but from or have an they which you were her she there been one all we their has would when who will more no if out so said what up its about into than them can only other time new some could these two may first then do any like my now over such our man me even most made after also did many before must through back years where much your way well down should because each just those people mr how too little state good very make world still own see men work long get here between both life being under never day same another know while last might us great old year off come since against go came right used take three".split())
# function words of other Latin-script languages that never occur as English words or in Arabic transliteration
_FOREIGN_WORDS = set("""
le les des du est une dans pour pas qui sur avec cette sont ont nous vous elle mais leur aux selon très être fait
yang dan dari untuk dengan tidak adalah akan kepada pada dalam atau juga bahwa telah oleh sesungguhnya barangsiapa itu ini
maka jika bagi kami mereka seorang
ve bir bu için ile değil olan gibi daha diye eden olarak
los las del una para pero como más está
und das ist nicht mit sich auf für dem ein eine
che sono della degli não uma com os
""".split())
_FOREIGN_CHARS = re.compile(r"[éèêëçñßğşıöœ]")   # none occurs in the published English translations (ü and ä do)
# honorifics written in Arabic inside English translations («Muhammad صلى الله عليه وسلم») say nothing about the language
_LANG_HONORIFICS = re.compile(r"ﷺ|صلى الله عليه وسلم|صلى الله عليه و سلم|رضي الله عنهما|رضي الله عنهم|رضي الله عنها|رضي الله عنه|"
                         r"عليهم السلام|عليه السلام|عليها السلام|سبحانه وتعالى|عز وجل|جل جلاله")


def detect_script_language(text: str) -> str:
    """'ar' (Arabic), 'en' (English) or 'other'. The input check rests on it: every Arabic text and every published
    English translation in the corpus is recognised (tested on all 40,457 records), and a text counts as another language
    only on positive evidence (that language's own words or letters), so English full of transliterated names stays
    English."""
    t = _LANG_HONORIFICS.sub(" ", strip_tashkeel(text))
    ar = len(_ARABIC_LETTERS.findall(t))
    la = len(_LATIN_LETTERS.findall(t))
    if ar == 0 and la == 0:
        return "ar" if _ARABIC_LETTERS.search(text) else "en" if _LATIN_LETTERS.search(text) else "ar"
    if ar >= 0.6 * la:
        marks = len(_URDU_PERSIAN_LETTERS.findall(t)) + sum(1 for w in t.split() if w in _PERSIAN_WORDS)
        return "other" if marks >= max(2, 0.02 * ar) else "ar"
    low = t.lower()
    words = re.findall(r"[a-zçéèêëñßğşıöœ']+", low)
    english = sum(1 for w in words if w in _EN_STOP)
    foreign = sum(1 for w in words if w in _FOREIGN_WORDS) + len(_FOREIGN_CHARS.findall(low))
    if (foreign >= 2 and foreign > english) or (foreign >= 1 and english == 0 and len(words) >= 3):
        return "other"
    return "en"


def to_arabic_digits(s: str) -> str:
    return s.translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


# --- matn extraction -------------------------------------------------------------

_DIA = "[\u064B-\u0652\u0670\u0640]*"


def _tolerant(pattern: str) -> str:
    """Make a plain-Arabic regex fragment tolerant to diacritics between letters."""
    out = []
    for ch in pattern:
        out.append(ch)
        if "\u0621" <= ch <= "\u064A":
            out.append(_DIA)
    return "".join(out)


_SALAT = "(?:" + "|".join(
    _tolerant(x) for x in ["صلى الله عليه وسلم", "صلى الله عليه وآله وسلم", "صلي الله عليه وسلم",
                           "صلى الله عليه و سلم", "صل الله عليه وسلم"]  # last two: common OCR renderings
) + "|ﷺ)"
_SAID = "(?:" + "|".join(
    _tolerant(x) for x in ["أنه قال", "كان يقول", "وهو يقول", "يقول", "قالت", "قال", "يخطب"]
) + ")"
_MATN_START = re.compile(rf"{_SALAT}\s*[،,]?\s*(?:{_tolerant('أنه')}\s+)?{_SAID}?\s*[:\"«]?\s*")
_LEADING_CONNECTORS = re.compile(
    rf"^(?:{_SAID}|{_tolerant('فقال')}|{_tolerant('ثم قال')}|[:\"«‏،,\s])+"
)
_TRAILING_MARKS = re.compile(r"[\u200f\u200e\u202b\u202c‏]+")


_QUOTED = re.compile(r'["“«]([^"“”«»]{8,})["”»]')


_ISNAD_HINT = re.compile("|".join(_tolerant(x) for x in [
    "حدثنا", "حدثني", "أخبرنا", "اخبرنا", "أخبرني", "اخبرني", "أنبأنا", "انبانا", "سمعت رسول الله", "سمعت النبي",
]))


def isnad_matn(text: str) -> str | None:
    """When the text carries a chain of narrators (حدثنا … عن … قال رسول الله ﷺ: …), return the matn
    (the saying itself); otherwise None. Diacritic-tolerant, so it works on vocalised text such as a
    sunnah.com screenshot or a copied page."""
    if not text or not _ISNAD_HINT.search(text):
        return None
    m = extract_matn(" ".join(text.split()))
    if not m or len(m) >= 0.9 * len(" ".join(text.split())):
        return None
    return m


def extract_matn(text: str) -> str:
    """Heuristically drop the isnad (chain of narrators) and keep the matn (saying).

    1. The open datasets mark the Prophet's words with ASCII quotes: `… قال "<matn>"`. When quoted
       segments exist and are a meaningful share of the text, they are the matn (joined if several).
    2. Otherwise take the text after the LAST `ﷺ قال`-style marker (texts with two chains repeat ﷺ).
    3. Otherwise return the whole text.
    """
    clean = _TRAILING_MARKS.sub("", text).replace("\u200f.\u200f", ".").strip()
    quotes = [q.strip(" .,:؛") for q in _QUOTED.findall(clean)]
    quotes = [q for q in quotes if len(q) >= 8]
    if quotes and sum(len(q) for q in quotes) >= 0.2 * len(clean):
        return _clean_matn(" ".join(quotes))
    best = ""
    for m in _MATN_START.finditer(clean):
        rest = _LEADING_CONNECTORS.sub("", clean[m.end():]).strip(' ."»«')
        if len(rest) >= 12:
            best = rest  # keep the last plausible start
    return _clean_matn(best or clean)


def _clean_matn(text: str) -> str:
    text = re.sub(r'["“”«»]', " ", text)
    text = re.sub(r"\s+\.\s+", " ", text)
    text = re.sub(r"\s+([،,.؛])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip(" .،")


# --- normalize_ar: the SINGLE entry point for every string that reaches the matcher --------------
# Used for the user's text (typed / OCR / URL) and for every hadith and ayah at ingestion (matn_norm).
# It is for matching only: the UI always displays the original texts.

_QUOTE_CHARS = re.compile(r"[«»\"“”„‟'‘’‚‛`´]")
_SYMBOLS = re.compile(r"[\U0001F000-\U0001FFFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200B-\u200F\u202A-\u202E\u2066-\u2069\uFDFD\uFDFA\uFDFB]")
# honorifics, in normalised spelling (applied after normalize_arabic), anywhere in the text
_HONORIFICS = re.compile(
    r"\b(?:صلي? (?:الله )?عليه (?:واله )?و ?سلم|صلي الله عليه واله|صلعم|"
    r"رضي الله عنهما|رضي الله عنهم|رضي الله عنها|رضي الله عنه|رضي الله عنهن|"
    r"عليه الصلاه والسلام|عليهما السلام|عليها السلام|عليه السلام|"
    r"رحمه الله تعالي|رحمه الله|رحمها الله|رحمهم الله|"
    r"سبحانه وتعالي|تبارك وتعالي|عز وجل|جل جلاله|جل وعلا)\b"
)
# narration lead-ins, only at the start (repeated until none is left)
_LEADINS = re.compile(
    r"^(?:حديث شريف|حديث|قال رسول الله|قال النبي|قال نبي الله|قال الرسول|قال عليه الصلاه والسلام|قال|يقول|"
    r"عن [\w ]{1,40}? (?:قال|قالت|انه قال|انها قالت|ان النبي|ان رسول الله)|"
    r"حدثنا [\w ]{1,120}?(?:قال|عن)|حدثني [\w ]{1,120}?(?:قال|عن)|اخبرنا [\w ]{1,120}?(?:قال|عن)|"
    r"روي [\w ]{1,40}?(?:ان|قال|عن)|رواه [\w ]{1,40}?(?:ان|قال|عن)|"
    r"رسول الله|النبي|نبي الله|انه قال|انها قالت)\s+"
)
_TRAILERS = re.compile(r"\s(?:رواه|اخرجه|متفق عليه|صححه|حسنه|ضعفه)\b.*$")


def normalize_ar(text: str, strip_leadins: bool = True) -> str:
    """Matching key for Arabic (and mixed) text. Never shown to users."""
    if not text:
        return ""
    t = _SYMBOLS.sub(" ", text)
    t = _QUOTE_CHARS.sub(" ", t)
    t = normalize_arabic(t)  # tashkeel, tatweel, letter forms, punctuation, digits, whitespace
    t = _HONORIFICS.sub(" ", t)
    t = _WS.sub(" ", t).strip()
    if strip_leadins:
        for _ in range(4):
            new = _LEADINS.sub("", t, count=1).strip()
            if new == t or len(new) < 8:
                break
            t = new
        t = _TRAILERS.sub("", t).strip()
    return _WS.sub(" ", t).strip()
