"""Quote extraction: honorifics and source notes in brackets are never taken as the quote, cross-references
(«بمثله») are never a match, and narrations of the same text are grouped."""
from __future__ import annotations

import pytest

from app.quotes import quote_candidates, substantive
from app.records import is_cross_reference


@pytest.mark.parametrize("span", [
    "peace be upon him", "PBUH", "may Allah be pleased with him", "صلى الله عليه وسلم", "رضي الله عنهما",
    "Sahih al-Bukhari 1", "Sahih Muslim, Book 1, Hadith 55", "رواه البخاري ومسلم", "رواه مسلم برقم ٥٥",
])
def test_formulas_and_references_are_not_quotes(span):
    assert not substantive(span)


@pytest.mark.parametrize("span", [
    "إنما الأعمال بالنيات", "المسلم أخو المسلم", "Actions are judged by intentions", "من حسن إسلام المرء تركه ما لا يعنيه",
])
def test_real_sayings_are_quotes(span):
    assert substantive(span)


def test_a_paraphrase_with_an_honorific_keeps_the_whole_sentence():
    text = ("During Hajj, the Prophet (peace be upon him) performed Tawaf by making seven rounds around the Kaaba, "
            "then prayed two rak'ahs behind Maqam Ibrahim.")
    spans = quote_candidates(text)
    assert spans and all("peace be upon him" != s for s in spans)
    assert spans[0].startswith("During Hajj")


def test_bracketed_quote_after_attribution_is_still_found():
    spans = quote_candidates("قال رسول الله صلى الله عليه وسلم: «إنما الأعمال بالنيات» (رواه البخاري)")
    assert spans[0] == "إنما الأعمال بالنيات"
    assert not any("رواه" in s for s in spans)


@pytest.mark.parametrize("matn,ref", [
    ("بمثله", True), ("فذكر نحوه", True), ("بهذا الحديث", True), ("بنحو حديثهم", True),
    ("العين حق", False), ("كل مسكر حرام", False), ("الحرب خدعه", False),
])
def test_cross_references_have_no_text_of_their_own(matn, ref):
    assert is_cross_reference(matn) is ref


def _rec(i: int, collection: str, number: str, matn: str):
    from app.records import Record

    return Record(id=i, kind="hadith", collection=collection, book_ar="", book_en="", number=number, chapter_ar="",
                  chapter_en="", text_ar=matn, matn_ar=matn, matn_norm=matn, text_en="", text_en_norm="", type_ar="",
                  type_en="", grades=[], source_url="")


def test_narrations_group_the_same_text_and_order_by_book():
    from app.store import rank_narrations

    long_ = "اذا اشتد الحر فابردوا بالصلاه فان شده الحر من فيح جهنم واشتكت النار الي ربها فقالت يا رب اكل بعضي بعضا"
    rec = _rec(1, "bukhari", "536", long_)
    cands = [
        _rec(2, "ibnmajah", "678", long_),
        _rec(3, "muslim", "617a", "واشتكت النار الي ربها فقالت يا رب اكل بعضي بعضا"),   # part of the longer text
        _rec(4, "tirmidhi", "1", "من غشنا فليس منا"),                                     # another hadith
        _rec(5, "nasai", "9", "بمثله"),                                                   # cross-reference
    ]
    got = [(r.collection, r.number) for r, _sim in rank_narrations(rec, cands, 10)]
    assert ("muslim", "617a") in got and ("ibnmajah", "678") in got
    assert ("tirmidhi", "1") not in got and ("nasai", "9") not in got


@pytest.mark.parametrize("quote,record,missing", [
    ("خير الأمور أوسطها", "إن أحسن الحديث كتاب الله وشر الأمور محدثاتها", True),
    ("خير الناس أنفعهم للناس", "كنتم خير أمة أخرجت للناس قال خير الناس للناس تأتون بهم", True),
    ("إنما الأعمال بالنية", "إنما الأعمال بالنيات وإنما لكل امرئ ما نوى", False),   # one-letter variant still counts
    ("الدين النصيحة", "الدين النصيحة قلنا لمن", False),
])
def test_a_short_arabic_quote_must_contain_every_word(quote, record, missing):
    from app.matcher import _short_quote_missing_word
    from app.normalize import normalize_ar

    assert _short_quote_missing_word(normalize_ar(quote), normalize_ar(record), "ar") is missing


def test_every_curated_saying_resolves_to_a_weak_state():
    # a curated circulated saying must never show a green "confirmed" state next to a not-authentic ruling
    import json
    from pathlib import Path

    from app.grades import is_unreliable

    seed = json.loads((Path(__file__).resolve().parents[1] / "ingest" / "seeds" / "rulings_seed.json").read_text(encoding="utf-8"))
    assert len(seed["items"]) >= 60
    for it in seed["items"]:
        assert it["grades"] and is_unreliable(it["grades"][0]["grade_ar"]), it["text_ar"]
        assert all(g["grade_ar"] and g["grader_ar"] and g["source_ar"] for g in it["grades"])
