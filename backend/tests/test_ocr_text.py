"""OCR post-processing and the full-hadith-with-isnad path, using the real transcriptions of a
sunnah.com screenshot of Sahih al-Bukhari 1 (qa/fixtures/images/sunnah-bukhari1.png)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.normalize import isnad_matn
from app.ocr import clean_lines, reflow

client = TestClient(app)

# what the vision model returned for the screenshot (exact)
VISION = """حَدَّثَنَا الْحُمَيْدِيُّ عَبْدُ اللَّهِ بْنُ الزُّبَيْرِ، قَالَ حَدَّثَنَا سُفْيَانُ، قَالَ حَدَّثَنَا يَحْيَى بْنُ سَعِيدٍ الْأَنْصَارِيُّ،
قَالَ أَخْبَرَنِي مُحَمَّدُ بْنُ إِبْرَاهِيمَ التَّيْمِيُّ، أَنَّهُ سَمِعَ عَلْقَمَةَ بْنَ وَقَّاصٍ اللَّيْثِيَّ، يَقُولُ سَمِعْتُ عُمَرَ بْنَ
الْخَطَّابِ - رضي الله عنه ـ عَلَى الْمِنْبَرِ قَالَ سَمِعْتُ رَسُولَ اللَّهِ صلى الله عليه وسلم يَقُولُ إِنَّمَا
الْأَعْمَالُ بِالنِّيَّاتِ، وَإِنَّمَا لِكُلِّ امْرِئٍ مَا نَوَى، فَمَنْ كَانَتْ هِجْرَتُهُ إِلَى دُنْيَا يُصِيبُهَا أَوْ إِلَى امْرَأَةٍ
يَنْكِحُهَا فَهِجْرَتُهُ إِلَى مَا هَاجَرَ إِلَيْهِ"""

# what Tesseract returned for the same screenshot (exact, including the diacritics-band junk lines)
TESSERACT = """حَدَكَنَا الحْتَيْرِيُ عَبْدُ الَو بْيُ الجيس قَالَ حَدَثَنَا سُفْيَانُ قَالَ حَدَثَنَا يجت بْنُ سَعِيدٍ الأنْصَاريُ
باض ا وسس؟ ادق قي ردس ااي سا سا سردي فر 2 ار ١ ان م ا
قال أخْبرني محمد بْنُ ِبْرَاهِيمَ الكَنِيُء انه سَمِعَ عَلْقمَة بُنَ وََاصٍ اللْيْْيَ يَقُول سَمِعْتُ غَمَرَ جُنَ
ب : 0 ِ هر بج سه . ٍ 2 1 0 م 22
الخطاب رضى الله عنه عَل اليد لمِنْبرِ قال سَمِعْتُ رَسُول الله صل الله عليه وسلم يَقُولُ إِنَمَا
ىس" و بد را 2 0 ا سر ان حراط ٠ه نْْ 1 ب ٍ ّي 1 نََ 3
الأَعْمَالُ بِالثيّاتِء وَإِنّمَا لكل امْرِئٍ مَا توى» فَمَنْ كانت مِجْرَثَهُ إلى دُنْيَا يُصِيبُهَا أو إلى امْرَأةٍ
يَنْكِحْهَا فَِجْرَثُهُ إلى مَا هَاجَرَ إلَيْهِ"""


def verify(text: str, via: str = "image") -> dict:
    r = client.post("/api/verify", json={"text": text, "lang": "ar", "explain": False, "via": via})
    assert r.status_code == 200, r.text
    return r.json()


def test_junk_lines_from_the_diacritics_band_are_dropped():
    cleaned = clean_lines(TESSERACT)
    assert "باض" not in cleaned and "حراط" not in cleaned and "22" not in cleaned
    assert cleaned.count("\n") == 4  # the five real lines survive


def test_quote_marks_survive_cleaning_and_english_lines_are_kept():
    assert '"' in clean_lines('قال رسول الله ﷺ " إنما الأعمال بالنيات "')
    assert clean_lines("None of you is a Muslim until he loves for his brother") == "None of you is a Muslim until he loves for his brother"


def test_reflow_joins_wrapped_lines_but_keeps_paragraphs():
    assert reflow("سطر أول\nيكمل هنا\n\nفقرة ثانية") == "سطر أول يكمل هنا\n\nفقرة ثانية"


@pytest.mark.parametrize("source", ["vision", "tesseract"])
def test_matn_is_found_inside_the_chain_of_narrators(source):
    text = reflow(clean_lines(VISION if source == "vision" else TESSERACT))
    matn = isnad_matn(text)
    assert matn and matn.split()[0].startswith("إِنَ") and "هَاجَرَ" in matn
    assert "حد" not in matn.split()[0]


def test_isnad_matn_ignores_text_without_a_chain():
    assert isnad_matn("إنما الأعمال بالنيات") is None
    assert isnad_matn("قال رسول الله ﷺ: الطهور شطر الإيمان") is None


@pytest.mark.parametrize("text,via", [
    (VISION, "image"),                               # vision transcription, multi-line as returned
    (reflow(clean_lines(VISION)), "image"),          # what the review box now shows
    (reflow(clean_lines(VISION)), "text"),           # the same full hadith pasted as text
])
def test_full_hadith_with_isnad_resolves_to_bukhari_1(text, via):
    out = verify(text, via)
    assert out["state"] == "verified", out["reason_en"]
    assert (out["source"]["collection"], out["source"]["number"]) == ("bukhari", "1")
    assert out["input_text"].split()[0].startswith("إِنَّمَا") or out["input_text"].split()[0].startswith("إنما")


def test_noisy_tesseract_transcription_still_resolves_to_bukhari_1():
    out = verify(reflow(clean_lines(TESSERACT)))
    assert out["state"] in ("verified", "partial"), out["reason_en"]
    assert (out["source"]["collection"], out["source"]["number"]) == ("bukhari", "1")
