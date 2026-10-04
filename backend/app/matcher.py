"""Retrieval cascade + calibrated confidence.

Every query goes through `normalize_ar` (Arabic) / `normalize_latin` (English) — the same functions
that produced the stored keys — then:

  1. exact / substring on the key            -> مؤيَّد بمصدر      (confidence >= 90)
  2. trigram word_similarity >= 0.6 with
     content-word coverage, or strong lexical -> مؤيَّد جزئيًا     (confidence >= 75)
  3. pgvector cosine >= 0.80                  -> غير مؤكد (closest) (confidence 50-74)
  4. otherwise                                -> لا مرجع – يُمتنع   (confidence < 50, nearest results)

The number shown to the user is the blended score (wording + meaning) clamped into the band of the
stage that admitted the record, so the Sources-page thresholds and the cascade agree.
Hadith, Qur'an and the curated rulings live in one table, so the same cascade covers all of them.
"""
from __future__ import annotations

from rapidfuzz import fuzz

from .chunking import windows
from .config import get_settings
from .embeddings import get_embedder
from .normalize import normalize_ar, normalize_latin
from .records import Record, is_cross_reference
from .store import get_store

TRIGRAM_MIN = 0.60      # stage 2: pg_trgm word_similarity
COSINE_MIN = 0.80       # stage 3: pgvector cosine …
LEX_FOR_SEMANTIC = 45.0  # … with at least some shared wording: MiniLM gives 0.85+ to formulaic but
                         # unrelated Arabic sentences («من … له …»), so meaning alone never admits a record
TRIGRAM_FOR_SEMANTIC = 0.55  # … and a trigram hit from the index (wording decides; meaning only ranks)
LEX_STRONG = 80.0       # stage 2 alternative: strong blended wording evidence (typos, extra words)
LEX_WITH_TRIGRAM = 70.0
EN_SEM_FOR_WORDING = 60.0  # English: shared common words alone are not evidence; the meaning must agree too

_STOP_AR = set("من في ما هذا هذه بين الي علي عن ان لا له لها او ثم قد كان قال ذلك الذي التي هو هي انا انت اذا حتي كل ولا الا لم لن ليس عند بعد قبل مع يا ثم فان ان".split())
_STOP_EN = set("the a an of to in and or is are was were be been for on at by with that this it he she they them his her its as not no until till who whom which what".split())


def _content_words(q: str, lang: str) -> list[str]:
    stop = _STOP_EN if lang == "en" else _STOP_AR
    return [w for w in q.split() if len(w) >= 3 and w not in stop]


SHORT_QUOTE_WORDS = 4   # an Arabic quote this short must contain every one of its content words to be confirmed


def _short_quote_missing_word(q: str, doc: str, lang: str) -> bool:
    """A short Arabic quote (≤ SHORT_QUOTE_WORDS content words) with a content word absent from the record:
    «خير الأمور أوسطها» is not «… وشر الأمور محدثاتها». Such a record can only be the closest text."""
    if lang == "en":
        return False   # English translations legitimately vary in wording
    words = _content_words(q, lang)
    if not 1 <= len(words) <= SHORT_QUOTE_WORDS:
        return False
    dwords = doc.split()
    for w in words:
        thr = 70 if len(w) <= 6 else 80
        if w not in dwords and not any(fuzz.ratio(w, x) >= thr for x in dwords):
            return True
    return False


def _lexical(q: str, doc: str, lang: str = "ar") -> float:
    """0-100. Character similarity against the best-aligned window of the document, blended with
    the share of the query's content words that appear (fuzzily) in that window. The blend stops a
    short generic phrase (e.g. «من الإيمان») from scoring high inside an unrelated long text."""
    if not q or not doc:
        return 0.0
    if len(doc) <= len(q):
        char = fuzz.ratio(q, doc)
        window = doc
    else:
        al = fuzz.partial_ratio_alignment(q, doc)
        char = al.score if al else fuzz.ratio(q, doc)
        ds, de = (al.dest_start, al.dest_end) if al else (0, len(doc))
        # expand the aligned span to word boundaries
        while ds > 0 and doc[ds - 1] != " ":
            ds -= 1
        while de < len(doc) and doc[de] != " ":
            de += 1
        window = doc[ds:de]
    if char >= 97 and len(q) >= 12:
        return 100.0
    words = _content_words(q, lang)
    if not words:
        return float(char)
    wwords = window.split()
    hit = 0
    for w in words:
        # one typo in a short word (e.g. بالنيه/بالنيات, امرء/امري) must still count as the same word
        thr = 70 if len(w) <= 6 else 80
        if w in wwords or any(fuzz.ratio(w, x) >= thr for x in wwords):
            hit += 1
    cov = 100.0 * hit / len(words)
    return float(min(100.0, 0.5 * char + 0.5 * cov))


def _semantic(cos: float, lang: str = "ar") -> float:
    # MiniLM cosines: unrelated Arabic ~0.3, unrelated English ~0.25; true English paraphrases
    # (translation variants of one hadith) typically land at 0.8-0.9, so English is rescaled wider.
    if lang == "en":
        return float(max(0.0, min(100.0, (cos - 0.25) / 0.65 * 100.0)))
    return float(max(0.0, min(100.0, (cos - 0.30) / 0.70 * 100.0)))


def _stage(r: Record, lex: float, score: int, lang: str, short_miss: bool = False) -> tuple[str, int]:
    """Admit the record through the cascade and clamp the score into that stage's band."""
    if r.stage == "exact":
        return "exact", max(score, 90)
    cos = r.semantic
    if lang == "en":
        # translations legitimately vary in wording; a wording match must also agree in meaning, and a match on
        # meaning alone is confirmed (or not) by the pipeline's match check
        lexical_ok = (lex >= LEX_WITH_TRIGRAM and _semantic(cos, lang) >= EN_SEM_FOR_WORDING) or score >= 75
    else:
        lexical_ok = (r.lexical >= TRIGRAM_MIN and lex >= LEX_WITH_TRIGRAM) or lex >= LEX_STRONG
    if lexical_ok and short_miss:
        return "semantic", min(score, 74)   # demote only: a short quote missing a word is at most the closest text
    if lexical_ok:
        return "trigram", min(max(score, 75), 100)
    if cos >= COSINE_MIN and lex >= LEX_FOR_SEMANTIC and r.lexical >= TRIGRAM_FOR_SEMANTIC:
        return "semantic", min(max(score, 50), 74)
    return "none", min(score, 49)


def confidence(lexical: float, semantic: float, lang: str = "ar") -> int:
    # Arabic input is compared with the source wording itself: wording dominates.
    # English input is always a translation (paraphrases are legitimate): meaning weighs as much as wording.
    if lang == "en":
        return int(round(0.5 * lexical + 0.5 * semantic))
    return int(round(0.75 * lexical + 0.25 * semantic))


def normalize_query(text: str, lang: str) -> str:
    """The single normalisation entry point for anything that reaches the matcher."""
    return normalize_latin(text) if lang == "en" else normalize_ar(text)


def search(text: str, lang: str = "ar", kinds: list[str] | None = None, limit: int = 5) -> list[dict]:
    """Return up to `limit` candidates sorted by stage then confidence,
    each {record, lexical, semantic, confidence, stage}."""
    get_settings()
    store = get_store()
    emb = get_embedder()
    norm = normalize_query(text, lang)
    if not norm:
        return []
    vec = emb.embed([" ".join(norm.split()[:40])])[0]
    by_id: dict[int, Record] = {}
    if len(norm) >= 12:
        for r in store.exact_search(norm, lang, kinds, 10):
            by_id[r.id] = r
    for r in store.vector_search(vec, lang, kinds, 25):
        if r.id in by_id:
            by_id[r.id].semantic = max(by_id[r.id].semantic, r.semantic)
        else:
            by_id[r.id] = r
    for r in store.lexical_search(norm, lang, kinds, 25):
        if r.id in by_id:
            by_id[r.id].lexical = max(by_id[r.id].lexical, r.lexical)
        else:
            by_id[r.id] = r
    # Rescore everything with both signals
    cands = []
    docs = {r.id: (r.text_en_norm if lang == "en" else r.matn_norm) for r in by_id.values()}
    missing = [r for r in by_id.values() if r.semantic == 0.0]
    if missing:
        flat, spans = [], []
        for r in missing:
            w = windows(docs[r.id], lang) or [" "]
            spans.append((len(flat), len(w)))
            flat.extend(w)
        sims = emb.embed(flat) @ vec
        for r, (a, n) in zip(missing, spans, strict=True):
            r.semantic = float(sims[a : a + n].max())
    # cross-references («بمثله», «فذكر نحوه») carry no text of their own
    for rid in [i for i, r in by_id.items() if r.kind == "hadith" and is_cross_reference(r.matn_norm)]:
        del by_id[rid]
    for r in by_id.values():
        lex = _lexical(norm, docs[r.id], lang)
        sem = _semantic(r.semantic, lang)
        score = confidence(lex, sem, lang)
        stage, conf = _stage(r, lex, score, lang, _short_quote_missing_word(norm, docs[r.id], lang))
        r.stage = stage
        # English admitted on meaning rather than shared wording: needs a strong model's confirmation (pipeline)
        meaning_only = lang == "en" and stage == "trigram" and lex < LEX_WITH_TRIGRAM
        cands.append({"record": r, "lexical": lex, "semantic": sem, "confidence": conf, "stage": stage, "meaning_only": meaning_only})
    # order: cascade stage, then confidence; ties: Qur'an, the Sahihayn, the curated seed, the Sunan
    prio = {"quran": 0, "bukhari": 1, "muslim": 2, "seed": 3}
    rank = {"exact": 0, "trigram": 1, "semantic": 2, "none": 3}
    cands.sort(key=lambda c: (rank[c["stage"]], -c["confidence"], prio.get(c["record"].collection, 9), c["record"].id))
    # de-duplicate identical matn across books (keep the highest ranked)
    seen: set[str] = set()
    out = []
    for c in cands:
        key = docs[c["record"].id][:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= limit:
            break
    return out
