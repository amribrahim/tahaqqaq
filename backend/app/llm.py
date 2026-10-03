"""Optional LLM layer behind one OpenAI-compatible client with automatic fallback.

The model NEVER grades. It receives the matched record and the scholars' ruling as fixed facts and
only writes the explanatory paragraph (labelled "شرح مولَّد بالذكاء الاصطناعي" in the UI) or
transcribes an image. Providers: gemini | groq | openrouter | cerebras (OpenAI-compatible HTTP) and
anthropic (official SDK). `LLM_PROVIDER=none` disables the layer; verdicts are unaffected either way."""
from __future__ import annotations

import base64
import json
import logging
import threading
import time
from dataclasses import dataclass

import httpx

from .config import Settings, get_settings

log = logging.getLogger(__name__)

SYSTEM = """You write short explanations for a hadith-verification tool used by preachers and content creators.
Hard rules:
- You NEVER grade a text yourself and never change, soften or add a ruling. The ruling and its source are given to you as facts; relay them as-is and attribute them to the named scholar/source.
- Do not quote text that is not in the input. Do not add additional hadiths, numbers or references.
- Write in the requested language (Arabic = fusha, no diacritics needed). 2-4 sentences, plain and respectful. No headings, no bullet lists.
- If the state is "abstain" or "referral", explain why the tool gives no verdict and what the user should do; never suggest a verdict.
Return JSON: {"explanation": "<text>"}"""

# Script families used to verify that an answer really is in the requested language
_SCRIPTS: dict[str, str] = {
    "ar": "arabic", "ur": "arabic", "fa": "arabic", "ps": "arabic", "ku": "latin",
    "ru": "cyrillic", "tg": "cyrillic", "zh": "cjk", "hi": "devanagari", "bn": "bengali", "am": "ethiopic",
}
_SCRIPT_RANGES: dict[str, str] = {
    "arabic": "\u0600-\u06FF\u0750-\u077F", "latin": "A-Za-z\u00C0-\u024F\u1E00-\u1EFF",
    "cyrillic": "\u0400-\u04FF", "cjk": "\u4E00-\u9FFF", "devanagari": "\u0900-\u097F",
    "bengali": "\u0980-\u09FF", "ethiopic": "\u1200-\u137F",
}


def script_matches(text: str, lang: str) -> bool:
    """True when the text is written mostly in the script of `lang` (unknown languages pass)."""
    import re

    family = _SCRIPTS.get(lang, "latin" if lang in LANGUAGES else "")
    if not family or not text:
        return True
    letters = re.findall(r"[^\W\d_]", text)
    if not letters:
        return False
    own = len(re.findall(f"[{_SCRIPT_RANGES[family]}]", text))
    # quoted Arabic wording may legitimately appear inside a non-Arabic explanation: require a clear majority
    return own >= 0.6 * len(letters)


# Explanation languages offered in the UI (code -> name the model is asked to write in)
LANGUAGES: dict[str, str] = {
    "ar": "Arabic (fusha)", "en": "English", "fr": "French", "ur": "Urdu", "id": "Indonesian", "ms": "Malay",
    "tr": "Turkish", "fa": "Persian", "bn": "Bengali", "hi": "Hindi", "de": "German", "es": "Spanish",
    "ru": "Russian", "zh": "Chinese (Simplified)", "sw": "Swahili", "so": "Somali", "ha": "Hausa",
    "am": "Amharic", "it": "Italian", "nl": "Dutch", "pt": "Portuguese", "ku": "Kurdish (Kurmanji)",
    "ps": "Pashto", "uz": "Uzbek", "tg": "Tajik",
}

GROUNDED_SYSTEM = """You write an extended explanation (شرح) of a hadith or Qur'anic verse for preachers and content creators,
inside a verification tool, by SUMMARISING THE PROVIDED SOURCE TEXT ONLY.
The source text ("source_text") is the شرح of the hadith or the tafsir of the verse, taken from الدرر السنية (an approved reference).
Hard rules:
- Use only information that is in source_text. Do not add meanings, rulings, hadiths, verses, numbers or scholars that are not in it.
- Never grade or re-grade; the ruling given in the facts is fixed and comes from the sources.
- If the ruling is fabricated/weak, say the text must not be attributed to the Prophet ﷺ.
- Write in the requested language. 150-260 words, 3-4 short paragraphs, each starting with a short heading line ending with ":"
  (e.g. "المعنى الإجمالي:", "غريب الألفاظ:", "الفوائد:"). No markdown, no bullet symbols.
Return JSON: {"explanation": "<text with paragraphs separated by blank lines>"}"""

EXTENDED_SYSTEM = """You write an extended explanation (شرح) of a hadith or Qur'anic verse for preachers and content creators,
inside a verification tool. The verification result, the ruling and the source are FIXED FACTS given to you.
Hard rules:
- Explain ONLY the matched source text given as "matched_text". Never explain the user's own wording when it differs.
- Never grade, re-grade, soften or dispute the ruling. Never add other hadiths, verse numbers, hadith numbers or references.
- Do NOT attribute statements to specific commentary books or named scholars (no "Ibn Hajar said", no "Fath al-Bari")
  unless such a text is given to you; write in a careful, general voice ("ظاهر الحديث يفيد", "ذكر الشرّاح أن…" is NOT allowed).
- If the text is a Qur'anic verse, give the general meaning only and say that the approved tafsir reference is dorar.net/tafseer.
- If the ruling is fabricated/weak (موضوع/ضعيف/باطل/لا أصل له), the explanation must say the text is not to be attributed to the Prophet ﷺ,
  and may explain why such texts spread; do not present its content as prophetic guidance.
- Write in the requested language. 150-260 words, plain prose in 3-4 short paragraphs. Start each paragraph with a short heading line
  ending with ":" (e.g. "المعنى الإجمالي:", "غريب الألفاظ:", "الفوائد:"), then the paragraph. No markdown, no bullet symbols.
Return JSON: {"explanation": "<text with paragraphs separated by blank lines>"}"""

EXTRACT_SYSTEM = """You clean text that came from OCR or from a web page, for a hadith-verification tool.
Tasks:
1. "cleaned_text": the same text with obvious OCR character errors in Arabic words fixed ONLY where you are certain
   (e.g. a broken letter, a missing «الله» in «صلى الله عليه وسلم»). Do not rephrase, reorder, add or drop sentences.
2. "segments": every religious quotation in the text — a hadith, a Qur'anic verse, or a saying attributed to the Prophet ﷺ,
   a companion or a scholar — as separate items, each with:
   - "text": the quotation itself, exactly as it appears (after the certain fixes), WITHOUT the attribution phrase
     («قال رسول الله ﷺ:», «عن فلان قال») and WITHOUT the narration trailer («رواه البخاري», «متفق عليه»),
   - "type": "hadith" | "quran" | "saying" | "other" (your best guess from the wording, never a ruling).
Rules: never invent text that is not in the input; never grade or comment; at most 8 segments, longest first.
Return JSON: {"cleaned_text": "...", "segments": [{"text": "...", "type": "..."}]}"""

TRANSLATE_SYSTEM = """You translate a short religious text (a hadith, a Qur'anic verse or a quoted saying) into English
for MATCHING ONLY inside a hadith-verification tool. Translate faithfully and literally; do not explain, correct,
complete, grade or identify the text, and do not substitute a well-known translation you remember.
Return JSON: {"language": "<English name of the input language>", "english": "<translation>"}"""

TRANSCRIBE_SYSTEM = """You transcribe images for a hadith-verification tool. Return ONLY the text visible in the
image, exactly as printed and in reading order: every line, including any chain of narrators (حدثنا … عن …),
headings and source notes. Keep Arabic diacritics if printed, keep quotation marks and punctuation as printed,
keep both Arabic and other languages. Do not translate, summarise, correct, reorder, grade or add anything.
If no text is readable return an empty string."""


@dataclass(frozen=True)
class Provider:
    name: str
    base: str
    key_attr: str
    model: str
    vision: bool
    json_mode: bool


PROVIDERS: dict[str, Provider] = {
    "gemini": Provider("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini_api_key",
                       "gemini-flash-lite-latest", vision=True, json_mode=True),  # lite: answers in ~2 s; flash-latest often exceeds the timeout
    "groq": Provider("groq", "https://api.groq.com/openai/v1", "groq_api_key",
                     "openai/gpt-oss-120b", vision=False, json_mode=True),
    # gemma (instruction-tuned, vision) rather than the free Qwen, which spends the token budget on hidden reasoning
    "openrouter": Provider("openrouter", "https://openrouter.ai/api/v1", "openrouter_api_key",
                           "google/gemma-4-26b-a4b-it:free", vision=True, json_mode=False),
    "cerebras": Provider("cerebras", "https://api.cerebras.ai/v1", "cerebras_api_key",
                         "llama-3.3-70b", vision=False, json_mode=True),
    "anthropic": Provider("anthropic", "", "anthropic_api_key", "claude-opus-5-5", vision=True, json_mode=True),
}

_RETRYABLE = {408, 409, 425, 429, 500, 502, 503, 504}
_COOLDOWN_S = 45.0
_TOTAL_BUDGET_S = 20.0  # the report never waits longer than this for an explanation


class LLMClient:
    """Tries the configured chain in order; a provider that rate-limits or errors is skipped for a while."""

    def __init__(self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self.s = settings or get_settings()
        self._cooldown: dict[str, float] = {}
        self._lock = threading.Lock()
        self._http = httpx.Client(timeout=self.s.llm_timeout, transport=transport)

    # -- configuration ----------------------------------------------------------------------------
    def chain(self) -> list[str]:
        primary = (self.s.llm_provider or "none").strip().lower()
        names = [primary] + [x.strip().lower() for x in self.s.llm_fallbacks.split(",") if x.strip()]
        if primary == "none" and self.s.anthropic_api_key:
            names = ["anthropic"] + names[1:]  # backwards compatible: ANTHROPIC_API_KEY alone still works
        out: list[str] = []
        for n in names:
            p = PROVIDERS.get(n)
            if p and getattr(self.s, p.key_attr, "") and n not in out:
                out.append(n)
        return out

    @property
    def enabled(self) -> bool:
        return bool(self.chain())

    def model_for(self, name: str) -> str:
        if name == (self.s.llm_provider or "").lower() and self.s.llm_model:
            return self.s.llm_model
        if name == "anthropic":
            return self.s.anthropic_model
        return PROVIDERS[name].model

    # -- core call --------------------------------------------------------------------------------
    def complete(self, system: str, user: list[dict] | str, *, json_mode: bool = False, need_vision: bool = False,
                 max_tokens: int = 1024) -> tuple[str, str] | None:
        """Return (text, "provider/model") from the first provider that answers, else None."""
        now = time.time()
        started = now
        for name in self.chain():
            p = PROVIDERS[name]
            if need_vision and not p.vision:
                continue
            if time.time() - started > _TOTAL_BUDGET_S:
                log.warning("llm budget exhausted before trying %s", name)
                break
            with self._lock:
                until = self._cooldown.get(name, 0.0)
            if until > now:
                continue
            try:
                if name == "anthropic":
                    text = self._anthropic(system, user, max_tokens)
                else:
                    text = self._openai_compatible(p, system, user, json_mode and p.json_mode, max_tokens)
                if text:
                    return text, f"{name}/{self.model_for(name)}"
            except _Retryable as e:
                log.warning("llm %s unavailable (%s); trying next provider", name, e)
                with self._lock:
                    self._cooldown[name] = time.time() + _COOLDOWN_S
            except Exception as e:  # noqa: BLE001 - the explanation is optional, never fail the report
                log.warning("llm %s failed (%s); trying next provider", name, e)
        return None

    def _openai_compatible(self, p: Provider, system: str, user: list[dict] | str, json_mode: bool, max_tokens: int) -> str:
        key = getattr(self.s, p.key_attr)
        body: dict = {
            "model": self.model_for(p.name),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        if p.name == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/tahqaq"
            headers["X-Title"] = "Tahaqqaq"
        try:
            r = self._http.post(f"{p.base}/chat/completions", json=body, headers=headers)
        except httpx.HTTPError as e:
            raise _Retryable(str(e)) from e
        if r.status_code in _RETRYABLE:
            raise _Retryable(f"HTTP {r.status_code}")
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        if isinstance(content, list):  # some providers return content parts
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        return content.strip()

    def _anthropic(self, system: str, user: list[dict] | str, max_tokens: int) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self.s.anthropic_api_key, timeout=max(self.s.llm_timeout, 25.0), max_retries=1)
        content = user if isinstance(user, list) else [{"type": "text", "text": user}]
        content = [_to_anthropic_part(c) for c in content]
        try:
            response = client.beta.messages.create(
                model=self.s.anthropic_model, max_tokens=max_tokens, system=system,
                output_config={"effort": "low"}, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                messages=[{"role": "user", "content": content}],
            )
        except anthropic.RateLimitError as e:
            raise _Retryable("rate limited") from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise _Retryable(f"HTTP {e.status_code}") from e
            raise
        except anthropic.APIConnectionError as e:
            raise _Retryable("connection error") from e
        if response.stop_reason == "refusal":
            return ""
        return "".join(b.text for b in response.content if b.type == "text").strip()


class _Retryable(Exception):
    pass


def _to_anthropic_part(part: dict) -> dict:
    if part.get("type") == "image_url":
        url = part["image_url"]["url"]  # data:<media>;base64,<data>
        media, b64 = url.split(";base64,", 1)
        return {"type": "image", "source": {"type": "base64", "media_type": media.removeprefix("data:"), "data": b64}}
    return part


_client: LLMClient | None = None
_client_lock = threading.Lock()


def get_client() -> LLMClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = LLMClient()
        return _client


def reset_client() -> None:
    global _client
    with _client_lock:
        _client = None


# -- public helpers used by the pipeline -----------------------------------------------------------
def explain(payload: dict, lang: str = "ar", mode: str = "brief", source_text: str | None = None) -> tuple[str, str] | None:
    """(explanation text, provider/model) or None when disabled or every provider failed.
    mode "brief": 2-4 sentences relaying the result; "extended": meaning, vocabulary and lessons of the matched text."""
    client = get_client()
    if not client.enabled:
        return None
    facts = json.dumps(payload, ensure_ascii=False)
    language = LANGUAGES.get(lang, lang if len(lang) > 2 else LANGUAGES["en"])
    extended = mode == "extended"
    base_system = (GROUNDED_SYSTEM if source_text else EXTENDED_SYSTEM) if extended else SYSTEM
    if source_text:
        payload = {**payload, "source_text": source_text[:9000]}
        facts = json.dumps(payload, ensure_ascii=False)
    system = base_system + (
        f"\n\nOUTPUT LANGUAGE: {language}. Write the ENTIRE explanation in {language} only, even though the facts are in Arabic: "
        f"render names, book titles and the ruling in {language} (transliterate where needed). "
        f"An answer in any other language is wrong."
    )
    user = f"Language: {language}\nFacts (do not alter): {facts}"
    for attempt in range(2):
        out = client.complete(system, user, json_mode=True, max_tokens=1600 if extended else 700)
        if not out:
            return None
        text, model = out
        try:
            parsed = json.loads(text)
            text = (parsed.get("explanation") or parsed.get("response") or "") if isinstance(parsed, dict) else text
        except ValueError:
            text = text.strip().strip("`").removeprefix("json").strip()
        text = text.strip()
        if text and script_matches(text, lang):
            return text, model
        log.warning("llm answer not in %s (attempt %s, %s); retrying", language, attempt + 1, model)
        user = f"Your previous answer was NOT in {language}. Answer again, in {language} only.\n" + user
    return None


def extract_segments(text: str) -> dict | None:
    """AI middle step for OCR / link / long input: certain-only OCR fixes + the quoted segments.
    Returns {"cleaned_text": str, "segments": [{"text","type"}], "model": str} or None.
    Every segment is validated against the source text (fuzzy containment) so nothing invented gets through."""
    client = get_client()
    if not client.enabled or not text.strip():
        return None
    out = client.complete(EXTRACT_SYSTEM, text[:6000], json_mode=True, max_tokens=1800)
    if not out:
        return None
    raw, model = out
    try:
        parsed = json.loads(raw)
    except ValueError:
        start, end = raw.find("{"), raw.rfind("}")
        try:
            parsed = json.loads(raw[start : end + 1]) if start >= 0 and end > start else {}
        except ValueError:
            return None
    if not isinstance(parsed, dict):
        return None
    from rapidfuzz import fuzz

    from .normalize import normalize_ar, normalize_latin

    src_ar, src_lat = normalize_ar(text, strip_leadins=False), normalize_latin(text)
    segments: list[dict] = []
    for seg in parsed.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        t = str(seg.get("text") or "").strip()
        if len(t) < 8:
            continue
        key_ar, key_lat = normalize_ar(t, strip_leadins=False), normalize_latin(t)
        grounded = (key_ar and fuzz.partial_ratio(key_ar, src_ar) >= 80) or (key_lat and fuzz.partial_ratio(key_lat, src_lat) >= 80)
        if not grounded:
            log.info("extract: dropped ungrounded segment %r", t[:60])
            continue
        kind = str(seg.get("type") or "other").lower()
        segments.append({"text": t, "type": kind if kind in ("hadith", "quran", "saying", "other") else "other"})
        if len(segments) >= 8:
            break
    cleaned = str(parsed.get("cleaned_text") or "").strip()
    if cleaned and fuzz.ratio(normalize_ar(cleaned, strip_leadins=False), src_ar) < 85:
        cleaned = ""  # a "cleaned" text that drifted from the input is not a cleaning
    return {"cleaned_text": cleaned, "segments": segments, "model": model}


def translate_for_matching(text: str) -> dict | None:
    """{"language", "english", "model"} for text that is neither Arabic nor English, or None."""
    client = get_client()
    if not client.enabled:
        return None
    out = client.complete(TRANSLATE_SYSTEM, text[:2000], json_mode=True, max_tokens=900)
    if not out:
        return None
    raw, model = out
    try:
        parsed = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
    except ValueError:
        return None
    english = str(parsed.get("english") or "").strip()
    if not english:
        return None
    return {"language": str(parsed.get("language") or "").strip(), "english": english, "model": model}


def transcribe_image(data: bytes, media_type: str = "image/png") -> str | None:
    """Vision transcription via the first vision-capable provider in the chain."""
    client = get_client()
    if not client.enabled:
        return None
    b64 = base64.standard_b64encode(data).decode()
    user = [
        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
        {"type": "text", "text": "Transcribe the text in this image."},
    ]
    out = client.complete(TRANSCRIBE_SYSTEM, user, need_vision=True, max_tokens=2048)
    return out[0] if out and out[0] else None
