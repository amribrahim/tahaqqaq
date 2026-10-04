"""Text to speech for the assistant's voice conversation, with a fallback chain:
  1. Groq Orpheus (canopylabs/orpheus-arabic-saudi, orpheus-v1-english), when voices are configured and the model terms
     were accepted in the Groq console,
  2. Piper, self-hosted on the server (Arabic ar_JO-kareem, English en_US-ryan): no quota, ~0.2 s per sentence,
     automatic Arabic diacritisation; this is the default voice,
  3. Gemini TTS, only when enabled (its free tier allows 10 requests a day, too few for a conversation),
  4. otherwise TTSUnavailable: the browser then speaks with the device's own voice.
Short texts only (one sentence at a time, so playback can start while the next sentence is generated); identical
requests are served from a small in-memory cache. Nothing is stored on disk."""
from __future__ import annotations

import base64
import io
import logging
import os
import re
import threading
import wave
from collections import OrderedDict
from functools import lru_cache

import httpx

from .config import get_settings

log = logging.getLogger(__name__)
MAX_CHARS = 400
GEMINI_MODEL = "gemini-2.5-flash-preview-tts"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/audio/speech"
GROQ_MODELS = {"ar": "canopylabs/orpheus-arabic-saudi", "en": "canopylabs/orpheus-v1-english"}

_cache: OrderedDict[tuple[str, str], tuple[bytes, str]] = OrderedDict()
_lock = threading.Lock()
_CACHE_SIZE = 200


class TTSUnavailable(Exception):
    pass


_ONES = ["صفر", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة"]
_TEENS = ["عشرة", "أحد عشر", "اثنا عشر", "ثلاثة عشر", "أربعة عشر", "خمسة عشر", "ستة عشر", "سبعة عشر", "ثمانية عشر", "تسعة عشر"]
_TENS = ["", "", "عشرون", "ثلاثون", "أربعون", "خمسون", "ستون", "سبعون", "ثمانون", "تسعون"]
_HUNDREDS = ["", "مئة", "مئتان", "ثلاثمئة", "أربعمئة", "خمسمئة", "ستمئة", "سبعمئة", "ثمانمئة", "تسعمئة"]


def arabic_number(n: int) -> str:
    """0..999999 in Arabic words, as a reader would say a hadith or page number («برقم أربعمئة وستة عشر»)."""
    if n < 10:
        return _ONES[n]
    if n < 20:
        return _TEENS[n - 10]
    if n < 100:
        return _TENS[n // 10] if n % 10 == 0 else f"{_ONES[n % 10]} و{_TENS[n // 10]}"
    if n < 1000:
        rest = n % 100
        return _HUNDREDS[n // 100] + (f" و{arabic_number(rest)}" if rest else "")
    if n < 1_000_000:
        k, rest = divmod(n, 1000)
        thousands = "ألف" if k == 1 else "ألفان" if k == 2 else f"{_ONES[k]} آلاف" if k <= 10 else f"{arabic_number(k)} ألفًا"
        return thousands + (f" و{arabic_number(rest)}" if rest else "")
    return str(n)


def speakable(text: str, lang: str = "ar") -> str:
    """Text as it should be read aloud: honorific glyphs spelled out, links and brackets dropped, and in Arabic numbers
    read as words («برقم 1907a» → «برقم ألف وتسعمئة وسبعة»)."""
    t = text.replace("ﷺ", " صلى الله عليه وسلم ").replace("«", "").replace("»", "")
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"[\[\]{}()\"“”]", " ", t)
    if lang == "ar":
        t = t.replace("الحكم:", "الحكم")
        t = re.sub(r"\d+[a-zA-Z]?", lambda m: arabic_number(int(re.sub(r"\D", "", m.group(0)))), t.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))
    return re.sub(r"\s+", " ", t).strip()[:MAX_CHARS]


def _wav(pcm: bytes, rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _groq(text: str, lang: str, client: httpx.Client) -> tuple[bytes, str] | None:
    s = get_settings()
    voice = s.tts_groq_voice_ar if lang == "ar" else s.tts_groq_voice_en
    if not (s.groq_api_key and voice):
        return None
    r = client.post(GROQ_URL, headers={"Authorization": f"Bearer {s.groq_api_key}"},
                    json={"model": GROQ_MODELS["ar" if lang == "ar" else "en"], "input": text, "voice": voice, "response_format": "wav"})
    if r.status_code != 200:
        log.warning("groq tts unavailable (%s): %s", r.status_code, r.text[:160])
        return None
    return r.content, "audio/wav"


@lru_cache(maxsize=2)
def _piper_voice(name: str):
    from piper import PiperVoice  # lazy: heavy import

    folder = get_settings().tts_piper_dir or os.environ.get("TTS_PIPER_DIR") or os.path.expanduser("~/.cache/piper")
    path = os.path.join(folder, f"{name}.onnx")
    return PiperVoice.load(path) if os.path.exists(path) else None


_piper_lock = threading.Lock()


def _piper(text: str, lang: str, client: httpx.Client) -> tuple[bytes, str] | None:
    s = get_settings()
    try:
        voice = _piper_voice(s.tts_piper_voice_ar if lang == "ar" else s.tts_piper_voice_en)
    except Exception as e:  # noqa: BLE001 - a missing or broken voice must not break the reply
        log.warning("piper unavailable: %s", e)
        return None
    if voice is None:
        return None
    buf = io.BytesIO()
    with _piper_lock, wave.open(buf, "wb") as w:
        voice.synthesize_wav(text, w)
    return buf.getvalue(), "audio/wav"


def _gemini(text: str, lang: str, client: httpx.Client) -> tuple[bytes, str] | None:
    s = get_settings()
    if not (s.tts_gemini and s.gemini_api_key):
        return None
    # a style instruction in English is followed but not read aloud (checked by transcribing the output)
    body = {"contents": [{"parts": [{"text": f"Say in a warm, calm and friendly voice: {text}"}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": s.tts_gemini_voice}}}}}
    # the key goes in a header, never in the URL (URLs end up in access logs)
    r = client.post(GEMINI_URL.format(model=GEMINI_MODEL), headers={"x-goog-api-key": s.gemini_api_key}, json=body)
    if r.status_code != 200:
        log.warning("gemini tts unavailable (%s): %s", r.status_code, r.text[:160])
        return None
    try:
        part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
        pcm = base64.b64decode(part["data"])
        rate = int(re.search(r"rate=(\d+)", part.get("mimeType", "")).group(1)) if "rate=" in part.get("mimeType", "") else 24000
    except (KeyError, IndexError, ValueError, AttributeError):
        return None
    return _wav(pcm, rate), "audio/wav"


def synthesize(text: str, lang: str, transport: httpx.BaseTransport | None = None) -> tuple[bytes, str]:
    text = speakable(text, lang)
    if not text:
        raise TTSUnavailable("empty")
    key = (lang, text)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    with httpx.Client(timeout=30.0, transport=transport) as client:
        for provider in (_groq, _piper, _gemini):
            try:
                out = provider(text, lang, client)
            except httpx.HTTPError as e:
                log.warning("tts %s failed: %s", provider.__name__, e)
                out = None
            if out:
                with _lock:
                    _cache[key] = out
                    while len(_cache) > _CACHE_SIZE:
                        _cache.popitem(last=False)
                return out
    raise TTSUnavailable("no provider answered")
