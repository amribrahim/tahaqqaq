"""Spec item 7: the same hadith in every input form resolves to the same record; noisy OCR
strings still resolve; an invented text still abstains after normalisation.
(Unit level: in-memory store. The real PNG and fixture pages are covered by tests/integration.)"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def verify(text: str, lang: str = "ar") -> dict:
    r = client.post("/api/verify", json={"text": text, "lang": lang, "explain": False})
    assert r.status_code == 200, r.text
    return r.json()


FORMS = {
    "full tashkeel + ﷺ + «»": "قال رسول الله ﷺ: «إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ، وَإِنَّمَا لِكُلِّ امْرِئٍ مَا نَوَى» رواه البخاري",
    "plain": "إنما الأعمال بالنيات وإنما لكل امرئ ما نوى",
    "narration lead-in + honorific": "عن عمر بن الخطاب رضي الله عنه قال: قال النبي صلى الله عليه وسلم: إنما الأعمال بالنيات وإنما لكل امرئ ما نوى",
    "simulated OCR line": "قال رسول الله صلى عليه وسلم: «إنما الأعمال بالنيات. وإنما لكل\nامرئ ما نوى» رواه البخاري",
    "fixture-page paragraph": "قال رسول الله صلى الله عليه وسلم: «إنما الأعمال بالنيات، وإنما لكل امرئ ما نوى» رواه البخاري ومسلم.",
}


@pytest.mark.parametrize("form", list(FORMS))
def test_every_input_form_resolves_to_the_same_record(form):
    out = verify(FORMS[form])
    assert out["state"] == "verified", (form, out["reason_en"])
    assert out["source"]["collection"] == "bukhari" and out["source"]["number"] == "1"
    assert out["grade"]["grade_ar"] == "صحيح"


NOISY_OCR = [
    "إنما الأعمال بالنيات وإنما لكل امرئ ما نوى",
    "انما الاعمال بالنيات وانما لكل امرىء ما نوى",
    "إنما الأعمال بالنيّات ، وإنما لكل امرئ ما نوى .",
    "إنما الاعمال بالنيات وانما لكل امرء ما نوي",
    "إنما الأعمال بالنيات و إنما لكل امرئ ما نوى",
    "انما الاعمال بالنيات. وانما لكل امرئ ما نوى",
    "إنما الأعمال بالنيات وإنما لكل امرئ مانوى",
    "إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ، وَإِنَّمَا لِكُلِّ امْرِئٍ مَا نَوَى",
    "| إنما الأعمال بالنيات وإنما لكل امرئ ما نوى |",
    "إنما الأعمال بالنيات ,وإنما لكل امرئ ما نوى 1",
]


@pytest.mark.parametrize("text", NOISY_OCR)
def test_noisy_ocr_strings_resolve_to_bukhari_1(text):
    out = verify(text)
    assert out["state"] in ("verified", "partial"), (text, out["reason_en"])
    assert out["source"]["collection"] == "bukhari" and out["source"]["number"] == "1"


@pytest.mark.parametrize("text", [
    "من قرأ هذا النص غُفر له كل ذنب",
    "قال رسول الله ﷺ: «من قرأ هذا النص غُفر له كل ذنب»",
    "من قرأ هذا الدعاء ونشره بين عشرة أشخاص فُرّج همّه في يومه",
])
def test_invented_text_still_abstains_after_normalisation(text):
    out = verify(text)
    assert out["state"] == "abstain", (text, out["reason_en"])
    assert out["grade"] is None and out["source"] is None
    assert not any(c["accepted"] for c in out["candidates"])


def test_cascade_stage_bands():
    """exact -> >=90, trigram -> >=75, semantic-only -> 50-74, none -> <50 (the Sources-page bands)."""
    assert verify("إنما الأعمال بالنيات")["confidence"] >= 90
    assert 75 <= verify("إنما الاعمال بالنيه ولكل امرء ما نوى يا إخوان")["confidence"]
    near = verify("النظافة من الإيمان")
    assert near["state"] in ("uncertain", "abstain") and near["confidence"] < 75
