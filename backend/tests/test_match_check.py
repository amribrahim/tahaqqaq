"""Retrieve-then-verify for English / machine-translated input: a model confirms or rejects the top records.
It never grades: a confirmed record is raised to "partial" at most, a rejected one is capped at "closest only"."""
from __future__ import annotations

import json

import httpx

from app import llm as llm_mod
from app import pipeline
from app.config import Settings
from app.llm import LLMClient
from tests.test_quotes import _rec


def _client(verdicts: list[dict]) -> LLMClient:
    body = json.dumps({"candidates": verdicts})
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": body}}]}))
    return LLMClient(Settings(_env_file=None, llm_provider="groq", groq_api_key="q", llm_fallbacks=""), transport=transport)


def _cand(i: int, conf: int, sem: float = 90.0, lex: float = 50.0, stage: str = "trigram") -> dict:
    return {"record": _rec(i, "bukhari", str(i), f"نص {i}"), "confidence": conf, "semantic": sem, "lexical": lex, "stage": stage}


def test_a_rejected_top_record_is_capped_and_a_confirmed_one_takes_its_place(monkeypatch):
    monkeypatch.setattr(llm_mod, "_client", _client([{"n": 1, "same": False}, {"n": 2, "same": True}]))
    cands = [_cand(1, 78), _cand(2, 55)]
    out = pipeline._check_match("The Prophet said ...", cands)
    assert out["outcome"] == "confirmed" and out["checked"] == 2
    assert cands[0]["record"].id == 2 and cands[0]["confidence"] == 75 and cands[0]["ai_confirmed"]
    assert cands[1]["confidence"] == pipeline.CHECK_REJECT_CAP and cands[1]["ai_rejected"]


def test_rejection_without_a_confirmed_alternative_leaves_only_a_closest_text(monkeypatch):
    monkeypatch.setattr(llm_mod, "_client", _client([{"n": 1, "same": False}]))
    cands = [_cand(1, 80)]
    out = pipeline._check_match("x", cands)
    assert out["outcome"] == "rejected" and pipeline._state_for(cands[0]["confidence"]) == "uncertain"


def test_exact_matches_and_weak_candidates_are_not_sent_to_the_model(monkeypatch):
    calls: list[int] = []

    def handler(r):
        calls.append(1)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(llm_mod, "_client", LLMClient(Settings(_env_file=None, llm_provider="gemini", gemini_api_key="g", llm_fallbacks=""),
                                                    transport=httpx.MockTransport(handler)))
    assert pipeline._check_match("x", [_cand(1, 95, stage="exact"), _cand(2, 40, sem=20.0, lex=10.0)]) is None
    assert calls == []


def test_without_a_provider_the_cascade_decides_alone(monkeypatch):
    monkeypatch.setattr(llm_mod, "_client", LLMClient(Settings(_env_file=None, llm_provider="none", anthropic_api_key="")))
    cands = [_cand(1, 78)]
    assert pipeline._check_match("x", cands) is None and cands[0]["confidence"] == 78


def test_a_light_fallback_model_can_reject_but_not_raise(monkeypatch):
    body = json.dumps({"candidates": [{"n": 1, "same": True}, {"n": 2, "same": False}]})
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": body}}]}))
    monkeypatch.setattr(llm_mod, "_client", LLMClient(Settings(_env_file=None, llm_provider="gemini", gemini_api_key="g", llm_fallbacks=""),
                                                    transport=transport))
    cands = [_cand(1, 55), _cand(2, 80)]
    pipeline._check_match("x", cands)
    by_id = {c["record"].id: c for c in cands}
    assert by_id[1]["confidence"] == 55 and not by_id[1].get("ai_confirmed")
    assert by_id[2]["confidence"] == pipeline.CHECK_REJECT_CAP


def test_a_quran_verse_is_never_raised_by_the_check(monkeypatch):
    monkeypatch.setattr(llm_mod, "_client", _client([{"n": 1, "same": True}]))
    verse = _cand(1, 60)
    verse["record"].kind = "quran"
    pipeline._check_match("We were on a campaign and had no wives with us ...", [verse])
    assert verse["confidence"] == 60 and not verse.get("ai_confirmed")
