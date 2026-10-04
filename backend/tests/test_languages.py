"""Languages: Arabic and English are matched directly; other languages go through a machine translation
to English for matching only (labelled), or abstain with a clear reason when no provider is available."""
from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.normalize import detect_script_language

client = TestClient(__import__("app.main", fromlist=["app"]).app)


@pytest.mark.parametrize("text,lang", [
    ("إنما الأعمال بالنيات", "ar"),
    ("None of you is a Muslim until he loves for his brother what he loves for himself.", "en"),
    ("Les actions ne valent que par les intentions, et chacun n'aura que ce qu'il a eu l'intention de faire", "other"),
    ("Sesungguhnya setiap amalan tergantung pada niatnya", "other"),
    ("Ameller ancak niyetlere göredir ve herkese niyet ettiği şey vardır", "other"),
    ("اعمال کا دارومدار نیتوں پر ہے اور ہر شخص کو وہی ملے گا جس کی اس نے نیت کی", "other"),
    ("کارها به نیت‌ها بستگی دارد", "other"),
])
def test_script_language_detection(text, lang):
    assert detect_script_language(text) == lang


def test_other_language_is_translated_for_matching_only(monkeypatch):
    from app import llm as llm_mod
    from app.config import Settings
    from app.llm import LLMClient

    translation = json.dumps({"language": "French", "english": "Actions are judged by intentions and every person will get what he intended"})

    def handler(confirm: bool):
        def h(request: httpx.Request) -> httpx.Response:
            system = json.loads(request.content)["messages"][0]["content"]
            if "SAME report" in system:   # the match check
                body = json.dumps({"candidates": [{"n": i, "same": confirm} for i in (1, 2, 3)]})
            else:
                body = translation
            return httpx.Response(200, json={"choices": [{"message": {"content": body}}]})
        return h

    fr = "Les actions ne valent que par les intentions, et chacun n'aura que ce qu'il a eu l'intention de faire"
    settings = Settings(_env_file=None, llm_provider="groq", groq_api_key="q", llm_fallbacks="")
    monkeypatch.setattr(llm_mod, "_client", LLMClient(settings, transport=httpx.MockTransport(handler(True))))
    out = client.post("/api/verify", json={"text": fr, "explain": False}).json()
    assert out["machine_translation"]["language"] == "French"
    assert out["input_text"] == fr                      # the user's own words are what the report shows
    assert out["state"] in ("verified", "partial") and out["source"]["collection"] == "bukhari"
    assert out["translation"] is None                   # a machine translation is never graded as the user's translation

    # the same input when the strong model says it is not the same report: closest text only, never an attribution
    monkeypatch.setattr(llm_mod, "_client", LLMClient(settings, transport=httpx.MockTransport(handler(False))))
    out = client.post("/api/verify", json={"text": fr, "explain": False}).json()
    assert out["state"] in ("uncertain", "abstain")


def test_other_language_without_a_provider_abstains_with_a_clear_reason(monkeypatch):
    from app import llm as llm_mod
    from app.config import Settings
    from app.llm import LLMClient

    monkeypatch.setattr(llm_mod, "_client", LLMClient(Settings(_env_file=None, llm_provider="none", anthropic_api_key="")))
    out = client.post("/api/verify", json={"text": "Sesungguhnya setiap amalan tergantung pada niatnya", "explain": False}).json()
    assert out["state"] == "abstain" and out["source"] is None and "Arabic or English" in out["reason_en"]
