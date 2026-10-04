"""Languages: Arabic texts are verified in the Arabic interface and English texts in the English one. Anything else is
refused with a clear message, never machine-translated (a translation would change the wording the verdict rests on).
The detector the check rests on recognises every Arabic text and every published English translation in the corpus."""
from __future__ import annotations

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from app import assistant, fetch_url
from app.normalize import detect_script_language

client = TestClient(__import__("app.main", fromlist=["app"]).app)


@pytest.mark.parametrize("text,lang", [
    ("إنما الأعمال بالنيات", "ar"),
    ("قال رسول الله ﷺ: إنما الأعمال بالنيات", "ar"),
    ("انما الاعمال بالنیات و انما لکل امری ما نوی", "ar"),                      # Arabic typed with Persian ya and kaf
    ("None of you is a Muslim until he loves for his brother what he loves for himself.", "en"),
    ("Allah's Messenger (ﷺ) said: War is deceit", "en"),
    ("Verily, he (Muhammad صلى الله عليه وسلم) is a madman!", "en"),              # an Arabic honorific inside English
    ("Subhanaka Allahumma Rabbana wa bihamdika, Allahumma ighfirli", "en"),     # transliteration is English text
    ("Les actions ne valent que par les intentions, et chacun n'aura que ce qu'il a eu l'intention de faire", "other"),
    ("Sesungguhnya setiap amalan tergantung pada niatnya", "other"),
    ("Sesungguhnya amal itu tergantung niatnya", "other"),
    ("Ameller ancak niyetlere göredir ve herkese niyet ettiği şey vardır", "other"),
    ("Ameller niyetlere göredir", "other"),
    ("Las obras dependen de las intenciones", "other"),
    ("اعمال کا دارومدار نیتوں پر ہے اور ہر شخص کو وہی ملے گا جس کی اس نے نیت کی", "other"),
    ("کارها به نیت‌ها بستگی دارد", "other"),
])
def test_script_language_detection(text, lang):
    assert detect_script_language(text) == lang


@pytest.mark.parametrize("ui,text,status", [
    ("ar", "إنما الأعمال بالنيات وإنما لكل امرئ ما نوى", 200),
    ("en", "The reward of deeds depends upon the intentions and every person will get the reward according to what he has intended", 200),
    ("ar", "Actions are but by intentions and every person will have only what he intended", 422),
    ("en", "إنما الأعمال بالنيات وإنما لكل امرئ ما نوى", 422),
    ("ar", "Les actions ne valent que par les intentions", 422),
    ("en", "Les actions ne valent que par les intentions", 422),
    ("ar", "اعمال کا دارومدار نیتوں پر ہے اور ہر شخص کو وہی ملے گا", 422),
])
def test_text_must_be_in_the_interface_language(ui, text, status):
    r = client.post("/api/verify", json={"text": text, "lang": ui, "explain": False})
    assert r.status_code == status, r.text
    if status == 422:
        detail = r.json()["detail"]
        assert detail["code"] == "wrong_language"
        assert ("الواجهة العربية" in detail["message"]) if ui == "ar" else ("English interface" in detail["message"])
    else:
        assert r.json()["source"]["collection"] == "bukhari"


def test_the_stream_refuses_the_wrong_language_before_starting():
    r = client.post("/api/verify/stream", json={"text": "إنما الأعمال بالنيات", "lang": "en", "explain": False})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "wrong_language"


def test_text_without_letters_is_not_refused():
    assert client.post("/api/verify", json={"text": "١٢٣ 456", "lang": "en", "explain": False}).status_code == 200


def test_sanad_verifies_in_the_interface_language_only():
    out = assistant.reply("هل يصح حديث إنما الأعمال بالنيات؟", "en")
    assert out["kind"] == "wrong_language" and out["lang"] == "en" and "English" in out["reply"]
    out = assistant.reply("Is this hadith authentic: actions are but by intentions?", "ar")
    assert out["kind"] == "wrong_language" and out["lang"] == "ar" and "العربية" in out["reply"]
    out = assistant.reply("هل يصح حديث إنما الأعمال بالنيات وإنما لكل امرئ ما نوى؟", "ar")
    assert out["kind"] == "verify" and out["report"]["source"]["number"] == "1"


SUNNAH_PAGE = """<html><body>
<div class="arabic_hadith_full"><span class="arabic_sanad">حَدَّثَنَا الْحُمَيْدِيُّ</span>
<span class="arabic_text_details">إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ</span></div>
<div class="english_hadith_full"><div class="hadith_narrated">Narrated 'Umar bin Al-Khattab:</div>
<div class="text_details">I heard Allah's Messenger (ﷺ) saying, "The reward of deeds depends upon the
   intentions"</div></div></body></html>"""


def test_sunnah_page_gives_the_text_in_the_interface_language():
    soup = BeautifulSoup(SUNNAH_PAGE, "lxml")
    ar_quote, ar_context = fetch_url.sunnah_texts(soup, "ar")
    en_quote, en_context = fetch_url.sunnah_texts(soup, "en")
    assert ar_quote == "إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ" and "Narrated" in ar_context
    assert en_quote.startswith("Narrated 'Umar bin Al-Khattab: I heard") and "  " not in en_quote and "بِالنِّيَّاتِ" in en_context
    assert detect_script_language(en_quote) == "en"
