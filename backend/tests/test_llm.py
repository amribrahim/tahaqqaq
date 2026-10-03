"""The LLM layer: provider chain, fallback on 429/5xx, JSON parsing, and that nothing leaks into verdicts."""
from __future__ import annotations

import json

import httpx

from app.config import Settings
from app.llm import LLMClient


def _settings(**kw) -> Settings:
    base = dict(llm_provider="gemini", llm_fallbacks="groq,openrouter", gemini_api_key="g", groq_api_key="q",
                openrouter_api_key="o", anthropic_api_key="", llm_timeout=5.0)
    base.update(kw)
    return Settings(_env_file=None, **base)


def _transport(statuses: dict[str, int], answer: str = '{"explanation": "شرح"}'):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        calls.append(host)
        code = next((c for h, c in statuses.items() if h in host), 200)
        if code != 200:
            return httpx.Response(code, json={"error": "nope"})
        return httpx.Response(200, json={"choices": [{"message": {"content": answer}}], "model": "m"})

    return httpx.MockTransport(handler), calls


def test_chain_only_lists_configured_providers():
    c = LLMClient(_settings(groq_api_key=""))
    assert c.chain() == ["gemini", "openrouter"]
    assert LLMClient(_settings(llm_provider="none", gemini_api_key="", groq_api_key="", openrouter_api_key="")).enabled is False


def test_anthropic_key_alone_still_enables_the_layer():
    c = LLMClient(_settings(llm_provider="none", llm_fallbacks="", gemini_api_key="", groq_api_key="", openrouter_api_key="", anthropic_api_key="a"))
    assert c.chain() == ["anthropic"]


def test_falls_back_on_rate_limit_and_server_errors():
    transport, calls = _transport({"googleapis": 429, "groq": 503})
    c = LLMClient(_settings(), transport=transport)
    out = c.complete("sys", "user", json_mode=True)
    assert out is not None
    text, model = out
    assert json.loads(text)["explanation"] == "شرح"
    assert model.startswith("openrouter/")
    assert [h.split(".")[0] for h in calls] == ["generativelanguage", "api", "openrouter"]
    # the rate-limited providers are skipped (cooldown) on the next call
    calls.clear()
    c.complete("sys", "user")
    assert calls == ["openrouter.ai"]


def test_returns_none_when_every_provider_fails():
    transport, _ = _transport({"googleapis": 500, "groq": 429, "openrouter": 502})
    c = LLMClient(_settings(), transport=transport)
    assert c.complete("sys", "user") is None


def test_vision_skips_providers_without_vision():
    transport, calls = _transport({"googleapis": 429})
    c = LLMClient(_settings(), transport=transport)
    out = c.complete("sys", [{"type": "text", "text": "x"}], need_vision=True)
    assert out is not None and out[1].startswith("openrouter/")
    assert "api.groq.com" not in calls


def test_extended_mode_uses_the_sharh_prompt_and_keeps_guardrails(monkeypatch):
    import json as _json

    from app import llm as llm_mod

    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(_json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"explanation": "المعنى الإجمالي:\\nشرح"}'}}]})

    client = LLMClient(_settings(), transport=httpx.MockTransport(handler))
    monkeypatch.setattr(llm_mod, "_client", client)
    out = llm_mod.explain({"state": "verified", "matched_text": "إنما الأعمال بالنيات"}, "ar", "extended")
    assert out and out[0].startswith("المعنى الإجمالي")
    system = seen[0]["messages"][0]["content"]
    assert "Never grade" in system and "dorar.net/tafseer" in system and seen[0]["max_tokens"] >= 1500
    brief = llm_mod.explain({"state": "verified"}, "ar", "brief")
    assert brief and "150-260 words" not in seen[1]["messages"][0]["content"]


def test_script_check_detects_wrong_language_answers():
    from app.llm import script_matches

    assert script_matches("Bu hadis Buhari tarafından sahih olarak rivayet edilmiştir.", "tr")
    assert not script_matches("تم التحقق من صحة الحديث وفقًا لتصنيف البخاري.", "tr")
    assert script_matches("يُذكر أن المصدر هو صحيح البخاري.", "ar")
    assert script_matches("Hadis ini sahih menurut al-Bukhari «إنما الأعمال بالنيات» dalam kitabnya.", "id")  # quoted Arabic allowed
    assert not script_matches("Hadith is sahih.", "ur")
    assert script_matches("Bu hadis sahihdir.", "xx")  # unknown language: no check


def test_wrong_language_answer_is_retried_then_rejected(monkeypatch):
    import json as _json

    from app import llm as llm_mod

    answers = iter(['{"explanation": "تم التحقق من صحة الحديث."}', '{"explanation": "Hadis, Buhari tarafından sahih kabul edilmiştir."}'])
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(_json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": next(answers)}}]})

    monkeypatch.setattr(llm_mod, "_client", LLMClient(_settings(), transport=httpx.MockTransport(handler)))
    out = llm_mod.explain({"state": "verified"}, "tr")
    assert out and out[0].startswith("Hadis")
    assert len(seen) == 2 and "NOT in Turkish" in seen[1]["messages"][1]["content"]
    assert "OUTPUT LANGUAGE: Turkish" in seen[0]["messages"][0]["content"]

    always_arabic = httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": '{"explanation": "نص عربي"}'}}]}))
    monkeypatch.setattr(llm_mod, "_client", LLMClient(_settings(), transport=always_arabic))
    assert llm_mod.explain({"state": "verified"}, "tr") is None  # never shown in the wrong language


def test_extract_segments_keeps_only_grounded_segments(monkeypatch):
    import json as _json

    from app import llm as llm_mod

    page = "مقال طويل عن النية. قال رسول الله ﷺ: «إنما الأعمال بالنيات، وإنما لكل امرئ ما نوى» رواه البخاري. وهذا كلام كثير آخر."
    answer = _json.dumps({"cleaned_text": page, "segments": [
        {"text": "إنما الأعمال بالنيات، وإنما لكل امرئ ما نوى", "type": "hadith"},
        {"text": "من عرف نفسه فقد عرف ربه", "type": "hadith"},   # not in the page: must be dropped
    ]}, ensure_ascii=False)
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": answer}}]}))
    monkeypatch.setattr(llm_mod, "_client", LLMClient(_settings(), transport=transport))
    out = llm_mod.extract_segments(page)
    assert out and [s["text"] for s in out["segments"]] == ["إنما الأعمال بالنيات، وإنما لكل امرئ ما نوى"]
    assert out["segments"][0]["type"] == "hadith" and out["model"].startswith("gemini/")


def test_extract_segments_rejects_a_rewritten_cleaned_text(monkeypatch):
    import json as _json

    from app import llm as llm_mod

    page = "قال رسول الله ﷺ: «الطهور شطر الإيمان»"
    answer = _json.dumps({"cleaned_text": "نص مختلف تمامًا كتبه النموذج من عنده", "segments": [{"text": "الطهور شطر الإيمان", "type": "hadith"}]}, ensure_ascii=False)
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": answer}}]}))
    monkeypatch.setattr(llm_mod, "_client", LLMClient(_settings(), transport=transport))
    out = llm_mod.extract_segments(page)
    assert out and out["cleaned_text"] == "" and len(out["segments"]) == 1
