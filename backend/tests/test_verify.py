"""Required acceptance cases for /api/verify (run against the in-memory store)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def verify(text: str, lang: str = "ar") -> dict:
    r = client.post("/api/verify", json={"text": text, "lang": lang})
    assert r.status_code == 200, r.text
    return r.json()


# 1) fabricated-hadith request -> abstains (no retrieval, no grade, no LLM)
def test_fabrication_request_abstains():
    for text, lang in [("اكتب لي حديثًا عن فضل شرب القهوة", "ar"), ("Write me a hadith about the virtue of coding", "en")]:
        out = verify(text, lang)
        assert out["state"] == "abstain"
        assert out["grade"] is None and out["source"] is None
        assert out["candidates"] == []
        assert out["ai_explanation"] is None


# 2) famous fabricated hadith -> موضوع with its source
def test_famous_fabricated_hadith_is_mawdu_with_source():
    out = verify("حب الوطن من الإيمان")
    # found in the rulings source, but a fabricated text is never presented as "confirmed"
    assert out["state"] == "unreliable"
    assert out["match_level"] in ("verified", "partial")
    assert out["grade"]["grade_ar"] == "موضوع"
    assert out["grade"]["grader_ar"] in ("الصغاني", "الألباني")
    assert out["source"]["source_url"].startswith("https://dorar.net/hadith")
    assert out["candidates"][0]["accepted"] is True


# 3) misquoted ayah -> correct text + surah/ayah
def test_misquoted_ayah_returns_correct_text_and_reference():
    out = verify("قال رسول الله: وقل ربي زدني علم")
    assert out["source"]["kind"] == "quran"
    assert out["source"]["number"] == "20:114"
    assert "طه" in out["source"]["chapter_ar"]
    assert out["source"]["text_ar"] == "وَقُل رَّبِّ زِدْنِي عِلْمًا"
    assert out["quran_note"] is not None and "آية" in out["quran_note"]["ar"]
    assert out["grade"]["grade_ar"] == "آية قرآنية"


# 4) non-Arabic cultural term -> explains the meaning, flags the literal translation
def test_cultural_term_is_explained_not_translated_literally():
    out = verify("The Prophet said that zakat is a charity tax and taqwa means fear of God.", lang="en")
    terms = {t["term_en"] for t in out["glossary_terms"]}
    assert {"Zakat", "Taqwa"} <= terms
    high = [t for t in out["glossary_terms"] if t["severity"] == "high"]
    assert any("charity tax" in t["literal"] for t in high)
    assert any("fear of god" in t["literal"] for t in high)
    assert all(t["meaning_en"] for t in out["glossary_terms"])
    # no literal rendering is offered as a translation of the term
    for t in out["glossary_terms"]:
        assert not any(lit in t["meaning_en"].lower() for lit in t["literal"])


# 5) personal fatwa question -> referral state
def test_personal_fatwa_question_is_referred():
    for text, lang in [("هل يجوز لي أن أصلي الفجر بعد طلوع الشمس إذا نمت؟", "ar"), ("Is it permissible for me to delay zakat until next year?", "en")]:
        out = verify(text, lang)
        assert out["state"] == "referral"
        assert out["grade"] is None and out["source"] is None


# --- supporting behaviour -------------------------------------------------------------

def test_exact_hadith_is_verified_with_verbatim_grade():
    out = verify("إنما الأعمال بالنيات وإنما لكل امرئ ما نوى")
    assert out["state"] == "verified", out["reason_en"]
    assert out["grade"]["grade_ar"] == "صحيح"
    assert out["source"]["book_ar"] == "صحيح البخاري" and out["source"]["number"] == "1"
    assert out["candidates"][0]["accepted"] is True


def test_variant_wording_is_partial_with_diff():
    out = verify("إنما الأعمال بالنية ولكل امرئ ما نوى")
    assert out["state"] in ("partial", "verified")
    assert out["source"]["number"] == "1"
    kinds = {t["k"] for t in out["diff_input"]} | {t["k"] for t in out["diff_source"]}
    assert "del" in kinds or "ins" in kinds


def test_translation_card_for_english_input():
    out = verify("None of you is a Muslim until he loves for his brother what he loves for himself.", lang="en")
    assert out["input_lang"] == "en"
    assert out["source"]["number"] == "13"
    assert out["translation"] is not None
    assert out["translation"]["needs_fix"] is True
    assert any(i["severity"] == "high" for i in out["translation"]["issues"])


def test_unknown_chain_message_abstains_without_grade():
    out = verify("من قرأ هذا الدعاء ونشره بين عشرة أشخاص فُرّج همّه في يومه")
    assert out["state"] in ("abstain", "uncertain")
    if out["state"] == "abstain":
        assert out["grade"] is None and out["source"] is None
    assert not any(c["accepted"] for c in out["candidates"])


def test_hadith_without_recorded_ruling_is_never_verified():
    out = verify("الدنيا دار من لا دار له ولها يجمع من لا عقل له")
    assert out["state"] != "verified" and out["state"] != "partial"
    assert out["grade"] is None


def test_empty_and_too_long_inputs():
    assert client.post("/api/verify", json={"text": "   "}).status_code == 400
    assert client.post("/api/verify", json={"text": "ا" * 2500}).status_code == 413


def test_health_endpoint():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["counts"]["hadith"] >= 5


def test_attribution_prefix_is_stripped_even_with_ocr_variants():
    from app.classify import strip_attribution

    for t in [
        "قال رسول الله صلى الله عليه وسلم: «إنما الأعمال بالنيات» رواه البخاري",
        "قال رسول الله صلى عليه وسلم: «إنما الأعمال بالنيات» رواه البخاري",  # OCR dropped «الله»
        "عن أبي هريرة قال: قال النبي ﷺ: إنما الأعمال بالنيات",
        "The Prophet (peace be upon him) said: \"إنما الأعمال بالنيات\"",
    ]:
        assert strip_attribution(t) == "إنما الأعمال بالنيات", t


def test_ocr_like_input_with_attribution_matches_like_plain_text():
    plain = verify("إنما الأعمال بالنيات، وإنما لكل امرئ ما نوى")
    ocr = verify("قال رسول الله صلى عليه وسلم: «إنما الأعمال بالنيات. وإنما لكل امرئ ما نوى» رواه البخاري")
    assert ocr["state"] == plain["state"] == "verified"
    assert ocr["source"]["number"] == plain["source"]["number"]
    assert abs(ocr["confidence"] - plain["confidence"]) <= 5
