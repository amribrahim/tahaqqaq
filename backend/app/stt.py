"""Speech to text for the assistant: Whisper large-v3, hosted on Groq (same key as the text models).

Voice is accepted in Arabic and English only, and only when the transcription is confident. In every other case a
clear error code is returned instead of a guess, so that nothing misheard is ever verified:
  stt_no_speech  silence, too short, or a phrase Whisper is known to invent on silence
  stt_unclear    low confidence or repetitive output
  stt_language   a language other than Arabic or English
  stt_too_long   longer than MAX_SECONDS, or a file over MAX_BYTES
  stt_unavailable  the speech service is not configured, rate-limited or down
The transcript is always shown to the user for confirmation before it is verified."""
from __future__ import annotations

import math
import re

import httpx

from .config import get_settings

URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODEL = "whisper-large-v3"
# No prompt is sent: in tests a hint prompt did not improve Arabic hadith transcription, and on silence Whisper echoed it
# back with moderate confidence ("The Prophet, peace be upon him, said."), which the confidence rules could not catch.
ALLOWED = {"arabic": "ar", "english": "en"}
MIN_SECONDS = 1.0
MAX_SECONDS = 60.0
MAX_BYTES = 5 * 1024 * 1024
NO_SPEECH = 0.6          # a segment more likely silent than this does not count as speech
MIN_LOGPROB = -1.0       # mean log-probability below this: the model was guessing
MAX_COMPRESSION = 2.4    # highly repetitive output is a known Whisper failure mode
# Phrases Whisper is known to produce on silence or noise (from subtitle data)
_HALLUCINATIONS = re.compile(
    r"اشتركوا في القناة|اشترك في القناة|ترجمة نانسي|شكرا للمشاهدة|شكراً للمشاهدة|موسيقى|thanks for watching|"
    r"thank you for watching|subscribe|subtitles by|amara\.org|^\W*(you|bye|thank you)\W*$", re.IGNORECASE)

MESSAGES = {
    "stt_no_speech": ("لم أسمع صوتًا واضحًا. أعد التسجيل أو اكتب النص.", "I could not hear clear speech. Record again or type the text."),
    "stt_unclear": ("لم أفهم التسجيل بوضوح. أعده بصوت أوضح أو اكتب النص.", "I could not understand the recording clearly. Record again more clearly or type the text."),
    "stt_language": ("الصوت متاح بالعربية والإنجليزية فقط. اكتب النص بدلًا من ذلك.", "Voice works in Arabic and English only. Please type the text instead."),
    "stt_too_long": ("التسجيل أطول من دقيقة. اختصره أو اكتب النص.", "The recording is longer than one minute. Shorten it or type the text."),
    "stt_unavailable": ("خدمة السماع غير متاحة الآن. اكتب النص بدلًا من ذلك.", "Voice input is unavailable right now. Please type the text instead."),
}


class STTError(Exception):
    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code, self.status = code, status

    def message(self, lang: str) -> str:
        ar, en = MESSAGES[self.code]
        return ar if lang == "ar" else en


def assess(result: dict) -> dict:
    """Apply the acceptance rules to a Whisper verbose_json result; raise STTError or return the accepted transcript."""
    text = re.sub(r"\s+", " ", (result.get("text") or "")).strip()
    duration = float(result.get("duration") or 0.0)
    segments = result.get("segments") or []
    if duration > MAX_SECONDS:
        raise STTError("stt_too_long", 413)
    speech = [s for s in segments if float(s.get("no_speech_prob", 0.0)) <= NO_SPEECH]
    if not text or duration < MIN_SECONDS or not speech or _HALLUCINATIONS.search(text):
        raise STTError("stt_no_speech", 422)
    lang = ALLOWED.get((result.get("language") or "").strip().lower())
    if not lang:
        raise STTError("stt_language", 422)
    total = sum(max(0.01, float(s.get("end", 0)) - float(s.get("start", 0))) for s in speech)
    logprob = sum(float(s.get("avg_logprob", -5.0)) * max(0.01, float(s.get("end", 0)) - float(s.get("start", 0))) for s in speech) / total
    if logprob < MIN_LOGPROB or any(float(s.get("compression_ratio", 1.0)) > MAX_COMPRESSION for s in speech):
        raise STTError("stt_unclear", 422)
    return {"text": text, "lang": lang, "duration": round(duration, 1), "confidence": round(100 * math.exp(logprob))}


def transcribe(data: bytes, filename: str, content_type: str, transport: httpx.BaseTransport | None = None) -> dict:
    key = get_settings().groq_api_key
    if not key:
        raise STTError("stt_unavailable", 503)
    if len(data) > MAX_BYTES:
        raise STTError("stt_too_long", 413)
    files = {"file": (filename or "audio.webm", data, content_type or "application/octet-stream")}
    form = {"model": MODEL, "response_format": "verbose_json", "temperature": "0"}
    try:
        with httpx.Client(timeout=40.0, transport=transport) as client:
            r = client.post(URL, headers={"Authorization": f"Bearer {key}"}, data=form, files=files)
    except httpx.HTTPError as e:
        raise STTError("stt_unavailable", 503) from e
    if r.status_code == 400:
        raise STTError("stt_no_speech", 422)   # unreadable or empty audio
    if r.status_code != 200:
        raise STTError("stt_unavailable", 503)
    return assess(r.json())
