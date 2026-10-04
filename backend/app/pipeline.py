"""The verification pipeline behind /api/verify.

Order: classify -> normalise -> retrieve (hadith + quran + seed) -> state from confidence ->
read the ruling VERBATIM from the matched record -> diff / translation card -> optional LLM text.
Nothing here persists user input."""
from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

from . import classify, llm, matcher
from .config import get_settings
from .diff import diff_tokens
from .fetch_url import pick_quote
from .grades import is_unreliable
from .normalize import detect_language, detect_script_language, isnad_matn, to_arabic_digits
from .quotes import is_marked, quote_candidates, substantive
from .records import Record
from .schemas import (
    CandidateOut,
    GradeOut,
    NarrationOut,
    SegmentOut,
    SourceOut,
    TranslationOut,
    VerifyResponse,
)
from .store import get_store
from .translation import glossary_notes, quoted_part, translation_card

Progress = Callable[[int, str], None]

STEP_NORMALIZE, STEP_MATCH, STEP_ATTRIBUTE, STEP_REPORT = 0, 1, 2, 3


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _state_for(conf: int) -> str:
    s = get_settings()
    if conf >= s.threshold_verified:
        return "verified"
    if conf >= s.threshold_partial:
        return "partial"
    if conf >= s.threshold_uncertain:
        return "uncertain"
    return "abstain"


_AR_LETTERS = re.compile(r"[\u0600-\u06FF]")


def _chapter_ar(r: Record) -> str:
    if r.kind == "seed":
        return ""
    if r.chapter_ar and _AR_LETTERS.search(r.chapter_ar):
        return r.chapter_ar
    sec = str((r.meta or {}).get("section") or "")
    return f"الكتاب رقم {to_arabic_digits(sec)}" if sec else ""


def _source_out(r: Record) -> SourceOut:
    return SourceOut(
        kind=r.kind, collection=r.collection, book_ar=r.book_ar, book_en=r.book_en, number=r.number,
        chapter_ar=_chapter_ar(r), chapter_en=r.chapter_en, type_ar=r.type_ar, type_en=r.type_en,
        text_ar=r.text_ar, matn_ar=r.matn_ar, text_en=r.text_en, text_en_quote=quoted_part(r.text_en or ""),
        source_url=r.source_url, alt_url=r.alt_url,
        note_ar=r.chapter_ar if r.kind == "seed" else "", note_en=r.chapter_en if r.kind == "seed" else "",
    )


def _grades_out(r: Record) -> list[GradeOut]:
    out = []
    for g in r.grades:
        g = dict(g)
        g.setdefault("url", r.source_url)
        if not g["url"]:
            g["url"] = r.source_url
        out.append(GradeOut(**{k: g.get(k, "") for k in GradeOut.model_fields}))
    return out


def _candidates_out(cands: list[dict], threshold: int) -> list[CandidateOut]:
    out = []
    for i, c in enumerate(cands, 1):
        r: Record = c["record"]
        out.append(CandidateOut(
            rank=i, collection=r.collection, text_ar=r.matn_ar[:220], text_en=quoted_part(r.text_en or "")[:220], book_ar=r.book_ar, book_en=r.book_en,
            number=r.number, kind=r.kind, confidence=c["confidence"], lexical=round(c["lexical"], 1),
            semantic=round(c["semantic"], 1), source_url=r.source_url, accepted=(i == 1 and c["confidence"] >= threshold),
        ))
    return out


def _reason(state: str, conf: int, r: Record | None, lang_in: str) -> tuple[str, str]:
    c_ar, c_en = to_arabic_digits(str(conf)) + "٪", f"{conf}%"
    if state == "referral":
        return ("هذا سؤال شخصي يستوجب فتوى من أهل العلم، وليس نصًا يُتحقق منه.",
                "This is a personal question that needs a scholar's fatwa, not a text to verify.")
    if state == "abstain" or r is None:
        return (f"أعلى تطابق {c_ar}، وهو أقل من حدّ القبول.", f"Highest match is {c_en}, below the acceptance threshold.")
    where_ar = f"{r.book_ar} ({to_arabic_digits(r.number)})"
    where_en = f"{r.book_en} {r.number}"
    if r.kind == "quran":
        where_ar, where_en = f"{r.chapter_ar} ({to_arabic_digits(r.number.split(':')[1])})", f"{r.chapter_en} {r.number}"
    if state == "verified":
        return (f"النص مطابق لما في {where_ar} بنسبة {c_ar}.", f"The text matches {where_en} at {c_en}.")
    if state == "partial":
        return (f"المعنى مطابق مع اختلاف في بعض الألفاظ عن {where_ar} ({c_ar}).",
                f"Meaning matches; some words differ from {where_en} ({c_en}).")
    return (f"لا يوجد نص بهذا اللفظ. أقرب نص في {where_ar} يقاربه ({c_ar}) ويحتاج إلى تثبّت.",
            f"No text has this wording. The closest is {where_en} ({c_en}) and needs review.")


def run(text: str, lang_ui: str = "ar", via: str = "text", extracted: str = "", progress: Progress | None = None,
        explain: bool = True) -> VerifyResponse:
    t0 = time.perf_counter()
    timings: dict[str, int] = {}
    settings = get_settings()
    report_id = uuid.uuid4().hex[:12]
    text = text.strip()
    lang_in = detect_language(text)
    # Arabic texts are matched with the Arabic records and English texts with their published English translations.
    # Other languages are not matched (the API refuses them before this point): a machine translation would change
    # the wording that the verdict rests on.

    def tick(step: int, label: str) -> None:
        if progress:
            progress(step, label)

    tick(STEP_NORMALIZE, "normalize")
    base = dict(id=report_id, input_text=text, input_lang=lang_in, via=via, extracted_text=extracted,
                threshold=settings.threshold_partial, created_at=_now())
    if detect_script_language(text) == "other":
        timings["total"] = int((time.perf_counter() - t0) * 1000)
        tick(STEP_REPORT, "report")
        return VerifyResponse(
            **base, state="abstain", confidence=0,
            reason_ar="نتحقق من النصوص العربية والإنجليزية فقط؛ الصق النص بالعربية في الواجهة العربية، أو بالإنجليزية في واجهة English.",
            reason_en="We check Arabic and English texts only: paste the text in Arabic in the Arabic interface, or in English in the English interface.",
            timings_ms=timings,
        )

    # 1) referral: personal fatwa question
    if classify.is_personal_fatwa(text) and not classify.looks_like_attribution(text):
        ra, re_ = _reason("referral", 0, None, lang_in)
        timings["total"] = int((time.perf_counter() - t0) * 1000)
        tick(STEP_REPORT, "report")
        return VerifyResponse(**base, state="referral", confidence=0, reason_ar=ra, reason_en=re_, timings_ms=timings)

    # 2) a request to fabricate a hadith is not a text to verify -> abstain, no retrieval, no LLM
    if classify.is_generation_request(text):
        timings["total"] = int((time.perf_counter() - t0) * 1000)
        tick(STEP_REPORT, "report")
        return VerifyResponse(
            **base, state="abstain", confidence=0,
            reason_ar="المُدخل طلب لإنشاء نص لا نصٌّ للتحقق منه. لا نُنشئ أحاديث ولا نُصدر حكمًا.",
            reason_en="The input asks to create a text rather than verify one. We do not generate hadiths or verdicts.",
            timings_ms=timings,
        )

    # A paste with extra material around the quote (commentary, attribution, OCR'd post, a page):
    # find the quoted/attributed spans, verify each, keep the best one.
    focus = text
    spans = quote_candidates(text)
    isnad = isnad_matn(text)  # full hadith with its chain of narrators (typed, pasted, OCR'd)
    has_inner_quote = any(len(sp) < 0.9 * len(text) for sp in spans) or bool(isnad)
    others: list[dict] = []
    seg_results: list[tuple[str, str, str, dict | None]] = []  # (text, type, origin, best match)
    extraction: dict | None = None
    if len(text) > 220 or via != "text" or has_inner_quote:
        # AI middle step: certain-only OCR fixes + the quoted segments, each validated against the input
        extraction = llm.extract_segments(text) if explain and (via != "text" or len(text) > 220) else None
        ai_spans = [(sg["text"], sg["type"]) for sg in (extraction or {}).get("segments", []) if substantive(sg["text"])]
        merged: list[tuple[str, str, str]] = [(t, ty, "ai") for t, ty in ai_spans]
        if isnad and not any(_same_span(isnad, m[0]) for m in merged):
            merged.insert(0, (isnad, "hadith", "rules"))
        for sp in spans:
            if not any(_same_span(sp, m[0]) for m in merged):
                merged.append((sp, "other", "rules"))
        if ai_spans and len(merged) > 8:
            merged = merged[:8]
        # a short typed text is itself a candidate: a fragment only replaces it when it is clearly the quote
        whole = text if via == "text" and len(text) <= 1500 else None
        focus, others, seg_results = _best_quote(text, lang_in, merged, whole=whole)
        focus = focus or pick_quote(text)
    query = classify.strip_attribution(focus) or focus
    # the attribution ("قال رسول الله") may sit outside the extracted span: look at both
    attributed = classify.looks_like_attribution(text) or classify.looks_like_attribution(focus)

    # 3) retrieval
    tick(STEP_MATCH, "match")
    t1 = time.perf_counter()
    if focus != text:
        lang_in = detect_language(focus)
        base["input_lang"] = lang_in
        if len(text) > 220 or via != "text":
            # long paste / link / image: the report is about the extracted span; keep the whole text as context
            base["input_text"] = focus
            if not base["extracted_text"]:
                base["extracted_text"] = text
    cands = matcher.search(query, lang=lang_in, kinds=None, limit=5)
    match_check = _check_match(query, cands) if lang_in == "en" else None
    if extraction:
        base["extraction_model"] = extraction.get("model")
        if extraction.get("cleaned_text") and extraction["cleaned_text"] != text:
            base["cleaned_text"] = extraction["cleaned_text"]
    base["segments"] = [_segment_out(t, ty, origin, m) for t, ty, origin, m in seg_results]
    # matches of the other quoted segments on the page/post are listed under nearest results too
    seen_ids = {c["record"].id for c in cands}
    for o in others:
        if o["record"].id not in seen_ids and len(cands) < 8:
            cands.append(o)
            seen_ids.add(o["record"].id)
    timings["match"] = int((time.perf_counter() - t1) * 1000)
    store = get_store()
    glossary = store.glossary()

    top = cands[0] if cands else None
    conf = top["confidence"] if top else 0
    state = _state_for(conf)
    rec: Record | None = top["record"] if top else None

    tick(STEP_ATTRIBUTE, "attribute")
    # Challenge rule: no hadith is attributed without a source AND a recorded ruling in the data.
    # A Sunan record with no grade can at most be shown as the "closest text" (uncertain).
    no_ruling = rec is not None and rec.kind == "hadith" and not rec.grades
    if no_ruling and state in ("verified", "partial"):
        state = "uncertain"
    # A matched text whose recorded ruling is fabricated/weak is NOT "confirmed": distinct state.
    match_level = ""
    if rec is not None and rec.grades and state in ("verified", "partial") and is_unreliable(rec.grades[0].get("grade_ar", "")):
        match_level, state = state, "unreliable"
    resp = VerifyResponse(**base, state=state, confidence=conf, match_level=match_level, reason_ar="", reason_en="",
                          candidates=_candidates_out(cands, settings.threshold_partial), timings_ms=timings, match_check=match_check)
    resp.reason_ar, resp.reason_en = _reason(state, conf, rec, lang_in)
    if match_check and top is not None and top.get("ai_confirmed") and state in ("partial", "unreliable"):
        resp.reason_ar += " وقارن نموذج لغوي النصين فوجدهما الرواية نفسها بلفظ مختلف؛ راجع النص المطابق قبل النشر."
        resp.reason_en += " A language model compared both texts and found the same report in other words; check the matched text before publishing."
    if state == "unreliable" and rec is not None:
        g0 = rec.grades[0]
        resp.reason_ar = (f"النص مطابق لما في {rec.book_ar} ({to_arabic_digits(rec.number)}) بنسبة {to_arabic_digits(str(conf))}٪، "
                          f"وحكم {g0.get('grader_ar', '')} عليه: {g0.get('grade_ar', '')}.")
        resp.reason_en = (f"The text matches {rec.book_en} {rec.number} at {conf}%; "
                          f"{g0.get('grader_en', '')} graded it: {g0.get('grade_en', '') or g0.get('grade_ar', '')}.")
    if no_ruling and rec is not None:
        resp.reason_ar = f"وُجد نص قريب في {rec.book_ar} ({to_arabic_digits(rec.number)}) لكن لم يُنقل له حكم معتمد في بياناتنا؛ راجع المصدر قبل النسبة."
        resp.reason_en = f"A close text exists in {rec.book_en} {rec.number} but no recorded ruling is in our data; check the source before attributing."

    if lang_in == "en":
        resp.glossary_terms = glossary_notes(text, glossary)

    if state == "abstain" or rec is None:
        # Never show a grade or attribution. Candidates stay visible for comparison only.
        tick(STEP_REPORT, "report")
        resp.ai_explanation, resp.ai_model = _explain(resp, rec, lang_ui, timings) if explain else (None, None)
        timings["total"] = int((time.perf_counter() - t0) * 1000)
        resp.timings_ms = timings
        return resp

    # 4) attribution: ruling read verbatim from the record
    resp.source = _source_out(rec)
    resp.grades = _grades_out(rec)
    resp.grade = resp.grades[0] if resp.grades else None
    resp.closest_only = state == "uncertain"
    if rec.kind == "hadith" and state in ("verified", "partial", "unreliable"):
        resp.narrations = _narrations_out(store.narrations(rec))

    if rec.kind == "quran" and (attributed or state in ("verified", "partial")):
        if attributed:
            resp.quran_note = {
                "ar": f"هذا النص آية قرآنية ({rec.chapter_ar}، الآية {to_arabic_digits(rec.number.split(':')[1])}) وليس حديثًا نبويًا.",
                "en": f"This text is a Qur'anic verse ({rec.chapter_en} {rec.number}), not a Prophetic hadith.",
            }

    if lang_in == "ar":
        resp.diff_input, resp.diff_source = diff_tokens(query, rec.matn_ar if rec.kind != "quran" else rec.text_ar, "ar")
    else:
        card = translation_card(query, rec, glossary)
        if card:
            resp.translation = TranslationOut(**card)

    tick(STEP_REPORT, "report")
    resp.ai_explanation, resp.ai_model = _explain(resp, rec, lang_ui, timings) if explain else (None, None)
    timings["total"] = int((time.perf_counter() - t0) * 1000)
    resp.timings_ms = timings
    return resp


# Retrieve-then-verify for English and machine-translated input: wording legitimately differs from the published
# translation, so meaning carries much of the score. A model checks whether the top records are the same report.
# It confirms (raise to "partial", the ruling still comes verbatim from the record) or rejects (cap at "closest only").
CHECK_MIN_SEMANTIC = 60.0   # scaled 0-100 (≈ cosine 0.64 on the English scale)
CHECK_MIN_LEXICAL = 25.0
CHECK_REJECT_CAP = 60       # a rejected record can at most be shown as the closest text (uncertain)
STRONG_JUDGES = ("groq/", "anthropic/")   # only these may raise a record; a lighter fallback model may only reject


def _cap_unconfirmed(cands: list[dict]) -> None:
    """An English match resting on meaning alone, not confirmed by a strong model, is at most the closest text."""
    partial = get_settings().threshold_partial
    changed = False
    for c in cands:
        if c.get("meaning_only") and not c.get("ai_confirmed") and c["confidence"] >= partial:
            c["confidence"], c["unconfirmed"], changed = partial - 1, True, True
    if changed:
        order = {id(c): k for k, c in enumerate(cands)}
        cands.sort(key=lambda c: (-c["confidence"], order[id(c)]))


def _check_match(query: str, cands: list[dict]) -> dict | None:
    try:
        return _run_match_check(query, cands)
    finally:
        _cap_unconfirmed(cands)


def _run_match_check(query: str, cands: list[dict]) -> dict | None:
    if not cands or not llm.get_client().enabled:
        return None
    eligible = [c for c in cands[:3] if c["stage"] != "exact" and c["confidence"] < get_settings().threshold_verified
                and c["semantic"] >= CHECK_MIN_SEMANTIC and c["lexical"] >= CHECK_MIN_LEXICAL]
    if not eligible:
        return None
    res = llm.check_match(query, [{"kind": c["record"].kind, "text_en": c["record"].text_en, "text_ar": c["record"].matn_ar}
                                  for c in eligible])
    if not res:
        return None
    partial = get_settings().threshold_partial
    strong = res["model"].startswith(STRONG_JUDGES)
    for i, c in enumerate(eligible, 1):
        same = res["verdicts"].get(i)
        if same is True and (not strong or c["record"].kind == "quran"):
            same = None   # a verse must match on wording alone; a light model's "same" does not raise anything
        if same is True and c["confidence"] < partial:
            c["confidence"], c["ai_confirmed"] = partial, True
        elif same is True:
            c["ai_confirmed"] = True
        elif same is False and c["confidence"] >= partial:
            c["confidence"], c["ai_rejected"] = min(c["confidence"], CHECK_REJECT_CAP), True
    order = {id(c): k for k, c in enumerate(cands)}
    cands.sort(key=lambda c: (-c["confidence"], not c.get("ai_confirmed", False), order[id(c)]))
    top = cands[0]
    outcome = "confirmed" if top.get("ai_confirmed") else "rejected" if any(c.get("ai_rejected") for c in eligible) else "kept"
    return {"model": res["model"], "outcome": outcome, "checked": len(eligible)}


def _narrations_out(found: list[tuple[Record, int]]) -> list[NarrationOut]:
    out = []
    for r, sim in found:
        g = r.grades[0] if r.grades else {}
        out.append(NarrationOut(collection=r.collection, book_ar=r.book_ar, book_en=r.book_en, number=r.number,
                                grade_ar=g.get("grade_ar", ""), grade_en=g.get("grade_en", ""), grader_ar=g.get("grader_ar", ""),
                                grader_en=g.get("grader_en", ""), similarity=sim, source_url=r.source_url))
    return out


def _same_span(a: str, b: str) -> bool:
    """Same quotation once attribution phrases/trailers and normalisation are removed (or one contains the other)."""
    from rapidfuzz import fuzz

    from .normalize import normalize_ar

    ka, kb = normalize_ar(classify.strip_attribution(a) or a), normalize_ar(classify.strip_attribution(b) or b)
    if not ka or not kb:
        return False
    return fuzz.ratio(ka, kb) >= 85 or (min(len(ka), len(kb)) >= 15 and (ka in kb or kb in ka))


SPAN_MARGIN = 10   # an unmarked fragment must beat the whole short text by this much to replace it


def _best_quote(text: str, lang_in: str, spans: list[tuple[str, str, str]] | None = None, whole: str | None = None
                ) -> tuple[str | None, list[dict], list[tuple[str, str, str, dict | None]]]:
    """Verify each quoted/attributed span (AI-extracted first, then rule-based); return the best span,
    the other spans' top matches, and every span with its own match.
    With `whole` (a short typed text), the text itself competes: a fragment wins only when it is presented as a
    quotation (quote marks, attribution) and scores at least as high, or scores SPAN_MARGIN points higher."""
    if spans is None:
        spans = [(sp, "other", "rules") for sp in quote_candidates(text)]
    if not spans:
        return None, [], []
    results: list[tuple[int, str, str, str, dict | None]] = []
    for span, ty, origin in spans[:8]:
        q = classify.strip_attribution(span) or span
        found = matcher.search(q, lang=detect_language(span), kinds=None, limit=1)
        results.append((found[0]["confidence"] if found else 0, span, ty, origin, found[0] if found else None))
    results.sort(key=lambda x: -x[0])
    best = results[0][1]
    if whole is not None:
        q = classify.strip_attribution(whole) or whole
        found = matcher.search(q, lang=detect_language(whole), kinds=None, limit=1)
        whole_conf = found[0]["confidence"] if found else 0
        top_conf = results[0][0]
        if not ((is_marked(text, best) and top_conf >= whole_conf) or top_conf >= whole_conf + SPAN_MARGIN):
            best = whole
    # one entry per matched source record (the highest-scoring span wins); unmatched spans keep their own entry
    kept: list[tuple[int, str, str, str, dict | None]] = []
    seen_rec: set[tuple[str, str]] = set()
    for row in results:
        c = row[4]
        key = (c["record"].collection, c["record"].number) if c and row[0] >= 50 else None
        if key and key in seen_rec:
            continue
        if key:
            seen_rec.add(key)
        kept.append(row)
    others = [c for conf, _s, _t, _o, c in kept[1:] if c is not None and conf >= 50]
    return best, others, [(s_, t_, o_, c) for _conf, s_, t_, o_, c in kept]


def _segment_out(text: str, ty: str, origin: str, m: dict | None) -> SegmentOut:
    if not m:
        return SegmentOut(text=text[:300], type=ty, origin=origin)
    r: Record = m["record"]
    return SegmentOut(text=text[:300], type=ty, origin=origin, confidence=m["confidence"], state=_state_for(m["confidence"]),
                      book_ar=r.book_ar, book_en=r.book_en, number=r.number, kind=r.kind, source_url=r.source_url)


def _explain(resp: VerifyResponse, rec: Record | None, lang_ui: str, timings: dict[str, int]) -> tuple[str | None, str | None]:
    if not llm.get_client().enabled:
        return None, None
    facts = {
        "state": resp.state, "confidence": resp.confidence, "input": resp.input_text,
        "matched_text": (rec.matn_ar if rec else None),
        "ruling": (resp.grade.model_dump() if resp.grade else None),
        # curated sayings carry an internal list number; the reference number is the ruling's (e.g. السلسلة الضعيفة 416)
        "source": ({"book": rec.book_ar, "number": (resp.grade.number if rec.collection == "seed" and resp.grade and resp.grade.number else rec.number),
                    "chapter": rec.chapter_ar, "type": rec.type_ar} if rec else None),
        "quran_note": resp.quran_note, "translation_issues": ([i.get("text_ar") for i in resp.translation.issues] if resp.translation else None),
    }
    t = time.perf_counter()
    out = llm.explain(facts, lang_ui)
    timings["llm"] = int((time.perf_counter() - t) * 1000)
    return (out[0], out[1]) if out else (None, None)


def run_streaming(text: str, lang_ui: str, via: str, extracted: str, explain: bool = True) -> Iterator[dict]:
    """Yield progress events live (the pipeline runs in a worker thread) then the final report."""
    import queue
    import threading

    q: queue.Queue[dict] = queue.Queue()

    def progress(step: int, label: str) -> None:
        q.put({"event": "progress", "data": {"step": step, "label": label}})

    def worker() -> None:
        try:
            result = run(text, lang_ui, via, extracted, progress=progress, explain=explain)
            q.put({"event": "result", "data": result.model_dump()})
        except Exception as e:  # noqa: BLE001
            q.put({"event": "error", "data": {"code": "sources_unreachable", "message": str(e)}})

    threading.Thread(target=worker, daemon=True).start()
    while True:
        ev = q.get()
        yield ev
        if ev["event"] in ("result", "error"):
            return
