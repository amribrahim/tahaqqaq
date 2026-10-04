"""The assistant: limited scope, deterministic routing, verification replies built from the report only, answers about
the tool only from the curated knowledge base, and speech-to-text that refuses rather than guesses."""
from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import assistant, ratelimit, stt
from app import llm as llm_mod
from app.config import Settings
from app.llm import LLMClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    """By default no model is configured: every path must still work."""
    monkeypatch.setattr(llm_mod, "_client", LLMClient(Settings(_env_file=None, llm_provider="none", anthropic_api_key="")))
    ratelimit.reset()


def _model(answer: dict, monkeypatch, provider: str = "groq"):
    body = json.dumps(answer, ensure_ascii=False)
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": body}}]}))
    settings = Settings(_env_file=None, llm_provider=provider, groq_api_key="q", gemini_api_key="g", llm_fallbacks="")
    monkeypatch.setattr(llm_mod, "_client", LLMClient(settings, transport=transport))


@pytest.mark.parametrize("message,has_report,kind", [
    ("قال رسول الله ﷺ: إنما الأعمال بالنيات", False, "verify"),
    ("هل يصح حديث اطلبوا العلم ولو في الصين", False, "verify"),
    ("إنما الأعمال بالنيات وإنما لكل امرئ ما نوى", False, "verify"),
    ("ما مصادر الأداة؟", False, "tool"),
    ("كيف تعمل المطابقة؟", False, "tool"),
    ("لماذا النتيجة مؤيد جزئيا؟", True, "report"),
    ("ما حكم صلاة الجماعة في المسجد؟", False, "fatwa"),
    ("السلام عليكم", False, "greeting"),
    ("Who won the world cup?", False, "ambiguous"),
])
def test_routing(message, has_report, kind):
    assert assistant.route(message, has_report) == kind


def test_the_hadith_is_taken_out_of_the_question():
    assert assistant.payload_of("هل يصح حديث اطلبوا العلم ولو في الصين؟") == "اطلبوا العلم ولو في الصين"
    assert assistant.payload_of("تحقق من هذا الحديث: «إنما الأعمال بالنيات»") == "إنما الأعمال بالنيات"


def test_a_verification_reply_quotes_the_report_only():
    out = client.post("/api/assistant", json={"message": "تحقق من حديث إنما الأعمال بالنيات", "lang": "ar"}).json()
    assert out["kind"] == "verify" and out["report"]["state"] == "verified"
    g = out["report"]["grade"]
    assert g["grade_ar"] in out["reply"] and g["source_ar"] in out["reply"]


def test_a_curated_fabricated_saying_is_flagged_with_its_ruling():
    out = assistant.reply("هل هذا حديث صحيح: حب الوطن من الإيمان", "ar")
    assert out["kind"] == "verify" and out["report"]["state"] == "unreliable"
    assert out["report"]["grade"]["grade_ar"] in out["reply"] and "لا يُنشر" in out["reply"]


def test_an_unknown_text_is_refused_not_guessed():
    out = assistant.reply("قال رسول الله ﷺ: من قرأ هذا النص غفر له كل ذنب وكتب له مثل أجر الأنبياء", "ar")
    assert out["report"]["state"] == "abstain" and out["report"]["grade"] is None and "لم أجد" in out["reply"]


def test_fixed_replies_for_fatwa_generation_and_other_topics():
    assert assistant.reply("ما حكم صلاة الجماعة في المسجد؟", "ar")["kind"] == "fatwa"
    assert assistant.reply("اكتب لي حديثا عن فضل الصدق", "ar")["kind"] == "generate"
    out = assistant.reply("Who won the world cup?", "en")
    assert out["kind"] == "out_of_scope" and "hadith" in out["reply"].lower()


def test_tool_question_without_a_model_returns_the_curated_text():
    out = assistant.reply("ما مصادر الأداة؟", "ar")
    assert out["kind"] == "tool" and "الدرر" in out["reply"] and out["sources"]


def test_tool_answer_with_an_invented_number_is_rejected(monkeypatch):
    _model({"answer": "تضم القاعدة ٩٩٩٬٩٩٩ حديثًا من الدرر السنية."}, monkeypatch)
    out = assistant.reply("ما مصادر الأداة؟", "ar")
    assert "٩٩٩" not in out["reply"] and "الدرر" in out["reply"]       # fell back to the curated paragraph


def test_tool_answer_from_the_sections_is_used(monkeypatch):
    _model({"answer": "تعتمد الأداة على الموسوعة الحديثية في الدرر السنية لأحكام العلماء، وعلى نصوص الكتب الستة."}, monkeypatch)
    out = assistant.reply("ما مصادر الأداة؟", "ar")
    assert out["reply"].startswith("تعتمد الأداة") and out.get("model", "").startswith("groq/")


def test_report_answer_that_changes_the_ruling_is_replaced(monkeypatch):
    report = client.post("/api/verify", json={"text": "إنما الأعمال بالنيات", "explain": False}).json()
    _model({"answer": "هذا الحديث ضعيف ولا يصح."}, monkeypatch)           # contradicts the recorded ruling
    out = assistant.reply("لماذا هذه النتيجة؟", "ar", report)
    assert out["kind"] == "report" and "ضعيف" not in out["reply"] and report["grade"]["grade_ar"] in out["reply"]


def test_rate_limit():
    for _ in range(30):
        assert client.post("/api/assistant", json={"message": "السلام عليكم"}).status_code == 200
    r = client.post("/api/assistant", json={"message": "السلام عليكم"})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"


# -- speech to text -------------------------------------------------------------------------------------
def _seg(start=0.0, end=3.0, logprob=-0.1, no_speech=0.01, cr=1.2):
    return {"start": start, "end": end, "avg_logprob": logprob, "no_speech_prob": no_speech, "compression_ratio": cr}


def test_a_clear_arabic_recording_is_accepted():
    out = stt.assess({"text": " قال رسول الله ﷺ إنما الأعمال بالنيات ", "language": "Arabic", "duration": 4.2, "segments": [_seg()]})
    assert out["lang"] == "ar" and out["text"].startswith("قال رسول الله") and out["confidence"] >= 85


@pytest.mark.parametrize("result,code", [
    ({"text": "Le Prophète a dit", "language": "French", "duration": 3, "segments": [_seg()]}, "stt_language"),
    ({"text": "you", "language": "English", "duration": 3, "segments": [_seg(no_speech=0.7, logprob=-0.7)]}, "stt_no_speech"),
    ({"text": "اشتركوا في القناة", "language": "Arabic", "duration": 3, "segments": [_seg()]}, "stt_no_speech"),
    ({"text": "قال", "language": "Arabic", "duration": 0.5, "segments": [_seg(end=0.5)]}, "stt_no_speech"),
    ({"text": "كلام غير واضح", "language": "Arabic", "duration": 3, "segments": [_seg(logprob=-1.4)]}, "stt_unclear"),
    ({"text": "الله الله الله الله", "language": "Arabic", "duration": 3, "segments": [_seg(cr=3.1)]}, "stt_unclear"),
    ({"text": "نص طويل", "language": "Arabic", "duration": 75, "segments": [_seg(end=75)]}, "stt_too_long"),
])
def test_unclear_recordings_are_refused(result, code):
    with pytest.raises(stt.STTError) as e:
        stt.assess(result)
    assert e.value.code == code and e.value.message("ar") and e.value.message("en")


def test_speech_service_unavailable(monkeypatch):
    monkeypatch.setattr(stt, "get_settings", lambda: Settings(_env_file=None, groq_api_key="q"))
    with pytest.raises(stt.STTError) as e:
        stt.transcribe(b"x" * 100, "a.webm", "audio/webm", transport=httpx.MockTransport(lambda r: httpx.Response(429)))
    assert e.value.code == "stt_unavailable"
    monkeypatch.setattr(stt, "get_settings", lambda: Settings(_env_file=None, groq_api_key=""))
    with pytest.raises(stt.STTError):
        stt.transcribe(b"x", "a.webm", "audio/webm")


def test_stt_endpoint_returns_a_clear_error(monkeypatch):
    def fail(*a, **k):
        raise stt.STTError("stt_language", 422)

    monkeypatch.setattr(stt, "transcribe", fail)
    r = client.post("/api/stt", files={"audio": ("a.webm", b"x" * 10, "audio/webm")}, data={"lang": "ar"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "stt_language"
    assert "العربية والإنجليزية" in r.json()["detail"]["message"]


# -- voice conversation: route-only, text to speech, misheard attributions ------------------------------
def test_route_only_says_whether_a_spoken_text_needs_confirmation():
    assert client.post("/api/assistant", json={"message": "قال رسول الله ﷺ إنما الأعمال بالنيات", "route_only": True}).json() == {"kind": "verify"}
    assert client.post("/api/assistant", json={"message": "ما مصادر الأداة؟", "route_only": True}).json() == {"kind": "tool"}


def test_a_misheard_attribution_before_the_honorific_is_dropped():
    from app.classify import looks_like_attribution, strip_attribution

    heard = "ورحمة الله صلى الله عليه وسلم إنما الأعمال بالنيات وإنما لكل مرء مهنوة"   # speech-to-text of «قال رسول الله ﷺ …»
    assert looks_like_attribution(heard)
    assert strip_attribution(heard) == "إنما الأعمال بالنيات وإنما لكل مرء مهنوة"
    out = client.post("/api/verify", json={"text": heard, "explain": False}).json()
    assert out["state"] in ("verified", "partial") and out["source"]["collection"] == "bukhari"


def test_tts_uses_gemini_wraps_pcm_in_wav_and_caches(monkeypatch):
    import base64

    from app import tts

    calls: list[str] = []
    urls: list[str] = []
    pcm = b"\x00\x01" * 2400

    def handler(r: httpx.Request) -> httpx.Response:
        calls.append(r.url.host)
        urls.append(str(r.url))
        body = {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/L16;codec=pcm;rate=24000",
                                                                       "data": base64.b64encode(pcm).decode()}}]}}]}
        return httpx.Response(200, json=body)

    monkeypatch.setattr(tts, "get_settings", lambda: Settings(_env_file=None, gemini_api_key="g", groq_api_key="q", tts_gemini=True,
                                                             tts_piper_dir="/nonexistent"))
    tts._cache.clear()
    tts._piper_voice.cache_clear()
    audio, mime = tts.synthesize("مؤيَّد بمصدر ﷺ", "ar", transport=httpx.MockTransport(handler))
    assert mime == "audio/wav" and audio[:4] == b"RIFF" and len(audio) > len(pcm)
    tts.synthesize("مؤيَّد بمصدر ﷺ", "ar", transport=httpx.MockTransport(handler))
    assert calls == ["generativelanguage.googleapis.com"]          # no Groq voice configured; second call served from cache
    assert not any("key=" in u for u in urls)                      # the key travels in a header, never in the URL
    assert "صلى الله عليه وسلم" in tts.speakable("قال ﷺ")


def test_tts_without_a_provider_lets_the_browser_speak(monkeypatch):
    from app import tts

    monkeypatch.setattr(tts, "get_settings", lambda: Settings(_env_file=None, gemini_api_key="", groq_api_key="", tts_piper_dir="/nonexistent"))
    monkeypatch.delenv("TTS_PIPER_DIR", raising=False)
    tts._cache.clear()
    tts._piper_voice.cache_clear()
    with pytest.raises(tts.TTSUnavailable):
        tts.synthesize("نص", "ar")
    r = client.post("/api/tts", json={"text": "نص", "lang": "ar"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "tts_unavailable"


@pytest.mark.parametrize("message,kind,expect", [
    ("السلام عليكم", "greeting", "سند"),
    ("كيف حالك؟", "how_are_you", "بخير"),
    ("الحمد لله بخير", "fine", "يسعدني"),
    ("بخير وأنت؟", "fine_and_you", "وأنا بخير"),
    ("اسمي أحمد", "name", "أحمد"),
    ("من أنت؟", "who", "سند"),
])
def test_sanad_small_talk(message, kind, expect):
    out = assistant.reply(message, "ar")
    assert out["kind"] == kind and expect in out["reply"]


def test_small_talk_never_becomes_a_verification():
    for m in ("الحمد لله بخير", "تمام الحمد لله", "I am looking for a hadith about honesty"):
        assert assistant.route(m, False) != "name"
    assert assistant.route("الحمد لله بخير", False) != "verify"


def test_numbers_are_read_as_arabic_words():
    from app.tts import arabic_number, speakable

    assert arabic_number(416) == "أربعمئة وستة عشر" and arabic_number(1907) == "ألف وتسعمئة وسبعة" and arabic_number(2) == "اثنان"
    assert speakable("الحكم: صحيح، في صحيح البخاري برقم 1.", "ar") == "الحكم صحيح، في صحيح البخاري برقم واحد."
    assert speakable("Bukhari number 1", "en") == "Bukhari number 1"


def test_piper_speaks_arabic_without_a_quota():
    import os

    from app import tts

    folder = os.environ.get("TTS_PIPER_DIR") or os.path.expanduser("~/.cache/piper")
    if not os.path.exists(os.path.join(folder, "ar_JO-kareem-medium.onnx")):
        pytest.skip("Piper voices are installed in the Docker image, not in every dev environment")
    tts._cache.clear()
    tts._piper_voice.cache_clear()
    audio, mime = tts.synthesize("مؤيَّد بمصدر.", "ar")
    assert mime == "audio/wav" and audio[:4] == b"RIFF" and len(audio) > 20_000


# -- corpus-aware spelling correction of Arabic voice transcripts ---------------------------------------
@pytest.mark.parametrize("heard,source,same", [
    ("مرئ", "امرئ", True), ("لو لا", "لولا", True), ("بن", "ابن", True), ("يصل", "يصلي", True),
    ("شفاع", "شفاعه", True), ("ظهر", "الظهر", True),
    ("بالنيه", "بالنيات", False),     # a real variant wording («إنما الأعمال بالنية»), never changed
    ("الليف", "الليث", False), ("دعوتي", "دعوه", False),
])
def test_spelling_blind_skeleton(heard, source, same):
    from app.normalize import normalize_ar
    from app.voice_fix import skeleton

    assert (skeleton([normalize_ar(w) for w in heard.split()]) == skeleton([normalize_ar(w) for w in source.split()])) is same


def test_snap_fixes_spelling_but_keeps_words_and_variants():
    from app.voice_fix import snap

    assert snap("إنما الأعمال بالنيات وإنما لكل مرئ ما نوى") == ("إنما الأعمال بالنيات وإنما لكل امرئ ما نوى", True)
    assert snap("إنما الأعمال بالنية وإنما لكل امرئ ما نوى")[1] is False      # a narration variant stays as said
    assert snap("كلام لا علاقة له بأي حديث نبوي معروف هنا")[1] is False         # no strong match: untouched
    fixed, changed = snap("إنما الأعمال بالنيات وإنما لكل مرئ ما نوى يا إخواني")
    assert changed and fixed.endswith("يا إخواني")                               # words the speaker added are kept


def test_stt_endpoint_returns_corrected_text_and_what_was_heard(monkeypatch):
    monkeypatch.setattr(stt, "transcribe", lambda *a, **k: {"text": "إنما الأعمال بالنيات وإنما لكل مرئ ما نوى", "lang": "ar", "duration": 3, "confidence": 90})
    out = client.post("/api/stt", files={"audio": ("a.webm", b"x" * 10, "audio/webm")}, data={"lang": "ar"}).json()
    assert out["corrected"] and out["text"].endswith("لكل امرئ ما نوى") and out["heard"].endswith("لكل مرئ ما نوى")
