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
from collections import OrderedDict
from dataclasses import dataclass

import httpx

from .config import Settings, get_settings

log = logging.getLogger(__name__)

SYSTEM = """You write short explanations for a hadith-verification tool used by preachers and content creators.
Hard rules:
- You NEVER grade a text yourself and never change, soften or add a ruling. The ruling and its source are given to you as facts; relay them as-is and attribute them to the named scholar/source.
- Say ONLY what the facts say: where the text was found (book and number), the ruling and who gave it, and what the reader should do. No commentary on the text's meaning, topic, importance or virtues, no praise, no general statements about Islam.
- Do not quote text that is not in the input. Do not add hadiths, numbers, dates or references that are not in the facts.
- Write in the requested language (Arabic = fusha, no diacritics needed). 2-4 sentences, plain and respectful. No headings, no bullet lists.
- If the state is "abstain" or "referral", explain why the tool gives no verdict and what the user should do; never suggest a verdict.
Return JSON: {"explanation": "<text>"}"""

FACTCHECK_SYSTEM = """You check a short explanation written by a hadith-verification tool against the facts it was given.
Flag ONLY statements that the facts do not support: an invented or changed ruling, grade, scholar, book, number or narration;
any claim about the text's meaning, topic, importance or virtues; anything that contradicts the facts.
Do NOT flag: relaying the given state, ruling and source (in any language or transliteration), saying the ruling is quoted
from the source, advising the reader to rely on the attribution, to cite or check the source, or to ask qualified scholars,
and explaining why the tool gives no verdict.
Return JSON: {"supported": true or false, "problems": ["<short description>", ...]}"""

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
    # the same Groq key, a smaller model with its own free quota: the last fallback when the others are used up
    "groq-lite": Provider("groq-lite", "https://api.groq.com/openai/v1", "groq_api_key",
                          "openai/gpt-oss-20b", vision=False, json_mode=True),
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
        if "groq" in out and "groq-lite" not in out:
            out.append("groq-lite")
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
                 max_tokens: int = 1024, prefer: tuple[str, ...] = (), exclude: tuple[str, ...] = ()) -> tuple[str, str] | None:
        """Return (text, "provider/model") from the first provider that answers, else None.
        `prefer` moves the named providers to the front (e.g. a stronger model for a judgement task); `exclude` skips
        providers that are not good enough for the task."""
        now = time.time()
        started = now
        chain = self.chain()
        chain = [n for n in prefer if n in chain] + [n for n in chain if n not in prefer and n not in exclude]
        for name in chain:
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
        if "gpt-oss" in body["model"]:
            body["reasoning_effort"] = "low"   # reasoning models: keep the hidden reasoning short so the answer fits
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
    # where a fixed wording built from the facts exists (a brief in Arabic or English), the light fallback model is
    # not used: in tests it confused the compiler with the narrator («الراوي البخاري»); the template is exact
    has_template = not extended and lang in ("ar", "en")
    for attempt in range(2):
        out = client.complete(system, user, json_mode=True, max_tokens=1600 if extended else 700,
                              exclude=("groq-lite",) if has_template else ())
        if not out:
            break
        text, model = out
        try:
            parsed = json.loads(text)
            text = (parsed.get("explanation") or parsed.get("response") or "") if isinstance(parsed, dict) else text
        except ValueError:
            text = text.strip().strip("`").removeprefix("json").strip()
        text = text.strip()
        if not text or not script_matches(text, lang):
            log.warning("llm answer not in %s (attempt %s, %s); retrying", language, attempt + 1, model)
            user = f"Your previous answer was NOT in {language}. Answer again, in {language} only.\n" + user
            continue
        problems = [] if extended else check_brief(text, payload) or fact_check(text, payload)
        if not problems:
            return text, model
        log.warning("brief explanation failed the fact check (attempt %s, %s): %s", attempt + 1, model, problems)
        user = ("Your previous answer had these problems: " + "; ".join(problems)
                + ". Rewrite it using ONLY the facts, with no commentary.\n" + user)
    if not extended:
        fallback = template_brief(payload, lang)
        if fallback:
            return fallback, "template (fact check)" if out else "template (models unavailable)"
    return None


# -- match check: is a retrieved record the same report as the user's text? ------------------------
MATCHCHECK_SYSTEM = """You compare a text that a user wants to verify with records found by a search engine (hadith
records with their English translation, or Qur'an verses). For each candidate decide whether it is the SAME report as
the user's text.
SAME means: the candidate contains the user's central statement or event - the same saying of the Prophet or the same
incident - even if worded differently, translated, shortened, or narrated by another Companion.
NOT the same: a candidate that only shares the topic (prayer, hajj, wrath, migration, fire ...), a few words, a general
idea, or a different incident - even when it gives the same ruling; a Qur'an verse when the user's text is a hadith
narrative or a saying that is not that verse.
When unsure, answer false. You never judge authenticity; you only compare the texts.
Return JSON: {"candidates": [{"n": <candidate number>, "why": "<at most 12 words>", "same": true or false}]}"""


_check_cache: OrderedDict[str, dict] = OrderedDict()
_check_lock = threading.Lock()


def check_match(user_text: str, candidates: list[dict]) -> dict | None:
    """{"verdicts": {n: bool}, "model": str} for candidates numbered from 1, or None when no provider answered."""
    client = get_client()
    if not client.enabled or not candidates:
        return None
    # English is compared with English: the Arabic is sent only for a record without a translation (it would double
    # the tokens, and the strong judge's free quota is counted in tokens)
    items = [{"n": i, "kind": c.get("kind", "hadith"), "text_en": (c.get("text_en") or "")[:700],
              **({} if c.get("text_en") else {"text_ar": (c.get("text_ar") or "")[:500]})}
             for i, c in enumerate(candidates, 1)]
    payload = json.dumps({"user_text": user_text[:1500], "candidates": items}, ensure_ascii=False)
    key = f"{id(client)}:{payload}"
    with _check_lock:
        if key in _check_cache:              # the same text checked again (a retry, a review PDF): no new model call
            _check_cache.move_to_end(key)
            return _check_cache[key]
    out = client.complete(MATCHCHECK_SYSTEM, payload, json_mode=True, max_tokens=700, prefer=("groq", "anthropic"))
    if not out:
        return None
    try:
        parsed = json.loads(out[0])
        rows = parsed.get("candidates", []) if isinstance(parsed, dict) else []
        verdicts = {int(r["n"]): bool(r["same"]) for r in rows if isinstance(r, dict) and "n" in r and "same" in r}
    except (ValueError, TypeError, KeyError):
        return None
    if not verdicts:
        return None
    res = {"verdicts": verdicts, "model": out[1]}
    with _check_lock:
        _check_cache[key] = res
        while len(_check_cache) > 256:
            _check_cache.popitem(last=False)
    return res


# -- fact checks for the brief explanation ---------------------------------------------------------
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_STRONG = {"صحيح", "حسن", "sahih", "authentic", "hasan"}
_WEAK = {"ضعيف", "موضوع", "منكر", "مكذوب", "باطل", "weak", "daif", "da'if", "fabricated", "mawdu", "forged", "baseless"}
_BOOK_PHRASES = ("صحيح البخاري", "صحيح مسلم", "صحيح الجامع", "صحيح ابن حبان", "صحيح ابن خزيمة", "صحيح الترغيب",
                 "صحيح أبي داود", "صحيح الترمذي", "صحيح النسائي", "صحيح ابن ماجه", "ضعيف الجامع", "ضعيف أبي داود",
                 "ضعيف الترمذي", "ضعيف النسائي", "ضعيف ابن ماجه", "sahih al-bukhari", "sahih muslim", "sahih bukhari")


def _words(text: str) -> set[str]:
    import re

    low = text.lower()
    for b in _BOOK_PHRASES:        # «صحيح البخاري» is a book title, not a grade
        low = low.replace(b, " ")
    return {w.strip("'’") for w in re.findall(r"[\w'’]+", low)} | {w[2:] for w in re.findall(r"\w+", low) if w.startswith("ال")}


def _grade_class(grade: str) -> str | None:
    w = _words(grade)
    if w & _WEAK:
        return "weak"
    if w & _STRONG:
        return "strong"
    return None


def check_brief(text: str, facts: dict) -> list[str]:
    """Rule checks: no grade that contradicts the recorded ruling, no verdict when the tool abstains, no invented numbers."""
    import re

    problems: list[str] = []
    ruling = facts.get("ruling") or {}
    words = _words(text)
    fact_class = _grade_class(f"{ruling.get('grade_ar', '')} {ruling.get('grade_en', '')}") if ruling else None
    if fact_class == "strong" and words & _WEAK:
        problems.append("it calls the text weak or fabricated, but the recorded ruling is " + ruling.get("grade_en", ""))
    if fact_class == "weak" and words & _STRONG:
        problems.append("it calls the text authentic, but the recorded ruling is " + ruling.get("grade_en", ""))
    if facts.get("state") in ("abstain", "referral") and words & (_STRONG | _WEAK):
        problems.append("it states a grade although the tool gives no verdict")
    allowed = set(re.findall(r"\d+", json.dumps(facts, ensure_ascii=False).translate(_DIGITS)))
    invented = [n for n in re.findall(r"\d+", text.translate(_DIGITS)) if n not in allowed]
    if invented:
        problems.append("it mentions numbers that are not in the facts: " + ", ".join(invented[:5]))
    return problems


def fact_check(text: str, facts: dict) -> list[str]:
    """Second pass by a model: flag claims the facts do not support (meaning, virtues, invented references).
    Runs only when there is a ruling or source to check against; an unavailable checker never blocks the answer."""
    if not (facts.get("ruling") or facts.get("source")):
        return []
    out = get_client().complete(FACTCHECK_SYSTEM, f"Facts: {json.dumps(facts, ensure_ascii=False)}\nExplanation: {text}",
                                json_mode=True, max_tokens=300)
    if not out:
        return []
    try:
        verdict = json.loads(out[0])
    except ValueError:
        return []
    if isinstance(verdict, dict) and verdict.get("supported") is False:
        return [str(p) for p in (verdict.get("problems") or ["unsupported claim"])][:4]
    return []


def template_brief(facts: dict, lang: str) -> str | None:
    """Fixed wording built only from the facts, used when the model's text fails the checks (Arabic and English)."""
    if lang not in ("ar", "en"):
        return None
    ar = lang == "ar"
    state = facts.get("state")
    g = facts.get("ruling") or {}
    src = facts.get("source") or {}
    book = (g.get("source_ar") if ar else g.get("source_en")) or src.get("book") or ""
    number = g.get("number") or src.get("number") or ""
    grade = g.get("grade_ar") if ar else g.get("grade_en")
    grader = g.get("grader_ar") if ar else g.get("grader_en")
    where = (f"{book} برقم {number}" if number else book) if ar else (f"{book}, number {number}" if number else book)
    if state == "referral":
        return ("هذا سؤال شخصي يحتاج إلى فتوى، والأداة لا تُفتي. نوصي بسؤال عالم موثوق." if ar else
                "This is a personal question that needs a fatwa, and the tool does not issue fatwas. Please ask a qualified scholar.")
    if state == "abstain":
        return ("لم نجد هذا النص في المصادر المعتمدة لدينا، لذلك نمتنع عن إصدار أي حكم. لا تنشره على أنه حديث حتى يتحقق منه أهل العلم." if ar else
                "This text was not found in our approved sources, so the tool gives no verdict. Do not publish it as a hadith until scholars have verified it.")
    if state == "uncertain":
        return ("لم نجد تطابقًا كافيًا، والنص المعروض أقرب نص فقط، فلا يُنسب حكمه إلى ما أدخلته. راجع المصدر أو اطلب مراجعة مختص." if ar else
                "No sufficient match was found. The text shown is only the closest one, so its ruling does not apply to your input. Check the source or request a specialist review.")
    if not grade or not book:
        return ("وُجد هذا النص في المصدر المعتمد الموضح أعلاه، والتفاصيل منقولة منه كما هي." if ar else
                "This text was found in the approved source shown above, and the details are quoted from it as recorded.")
    by = (f" ({grader})" if grader else "")
    if state == "unreliable":
        return (f"وُجد هذا النص في {where}، وحكمه: {grade}{by}، كما ورد في المصدر. لذلك لا يُنشر على أنه حديث ثابت." if ar else
                f"This text is recorded in {where} with the ruling: {grade}{by}, as stated in the source. It should not be published as an established hadith.")
    if state == "partial":
        return (f"وُجد هذا النص في {where} بلفظ يختلف قليلًا عمّا أدخلته، وحكمه: {grade}{by}. يُستحسن نشره بلفظ المصدر الموضح أعلاه." if ar else
                f"This text was found in {where} with slightly different wording, and its ruling is: {grade}{by}. Publish it in the source's wording shown above.")
    return (f"وُجد هذا النص في {where}، وحكمه: {grade}{by}، والحكم منقول من المصدر كما هو. اذكر المصدر عند النشر." if ar else
            f"This text was found in {where}, and its ruling is: {grade}{by}, quoted from the source as recorded. Cite the source when you publish it.")


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
