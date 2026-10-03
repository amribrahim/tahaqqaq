"""الدرر السنية client, against saved real pages (no network): rulings, شرح and tafsir sections,
and that the grounded extended explanation only uses the retrieved source text."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app import dorar
from app.dorar import DorarClient, parse_cards, parse_explain, parse_tafseer

FIX = json.loads((Path(__file__).parent / "fixtures" / "dorar_fixtures.json").read_text(encoding="utf-8"))
BUKHARI_1 = "إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ، وَإِنَّمَا لِكُلِّ امْرِئٍ مَا نَوَى، فَمَنْ كَانَتْ هِجْرَتُهُ إِلَى دُنْيَا يُصِيبُهَا"


def _transport() -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/hadith/search":
            return httpx.Response(200, text=FIX["search"])
        if path.startswith("/hadith/explain/"):
            return httpx.Response(200, text=FIX["explain_70031"])
        if path == "/tafseer/20/12":
            return httpx.Response(200, text=FIX["tafseer_20_12"])
        if path.startswith("/tafseer/20/"):
            n = int(path.rsplit("/", 1)[1])
            # synthesise section titles: section n covers ayat (8n-7 .. 8n) up to 12, which covers 90-94
            lo, hi = (8 * n - 7, 8 * n) if n < 12 else (90, 94)
            return httpx.Response(200, text=f"<title>الدرر السنية - موسوعة التفسير - سورةُ طه الآيات ({lo}-{hi})</title>")
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_search_cards_carry_every_field_and_the_sharh_id():
    cards = parse_cards(FIX["search"])
    assert len(cards) >= 10
    bukhari = next(c for c in cards if c["book"] == "صحيح البخاري" and c["number"] == "1")
    assert bukhari["scholar"] == "البخاري" and "صحيح" in bukhari["grade"] and bukhari["narrator"]
    assert any(c["xplain"] for c in cards)
    assert all(c["scholar"] != c["grade"] for c in cards)  # «المحدث» is not read from «خلاصة حكم المحدث»


def test_explain_page_gives_ruling_and_sharh():
    e = parse_explain(FIX["explain_70031"])
    assert e["scholar"] == "البخاري" and e["book"] == "صحيح البخاري" and e["grade"] == "صحيح"
    assert e["sharh"].startswith("هذا الحديثُ العَظيمُ") and len(e["sharh"]) > 300


def test_tafseer_section_text_starts_at_the_tafsir_not_the_menu():
    t = parse_tafseer(FIX["tafseer_20_12"])
    assert t["range"] == (90, 94)
    assert t["text"].startswith("غريب الكلمات:") and "اختر السورة" not in t["text"] and len(t["text"]) > 2000


def test_rulings_for_ranks_the_compilers_own_entry_first():
    c = DorarClient(transport=_transport(), cache=False)
    info = c.rulings_for(BUKHARI_1, "صحيح البخاري", "1")
    assert info["best"]["book"] == "صحيح البخاري" and info["best"]["number"] == "1"
    assert info["search_url"].startswith("https://dorar.net/hadith/search?q=")
    assert len(info["cards"]) <= 4


def test_repeated_entries_on_the_page_are_shown_once():
    page = FIX["search"]
    chunks = page.split('<div class="border-bottom py-4')
    doubled = chunks[0] + "".join('<div class="border-bottom py-4' + c for c in chunks[1:] * 2)  # every card twice
    once = parse_cards(page)
    assert len(parse_cards(doubled)) == len(once)
    keys = [(c["scholar"], c["book"], c["number"], c["text"]) for c in once]
    assert len(keys) == len(set(keys))
    c = DorarClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=doubled)), cache=False)
    shown = c.rulings_for(BUKHARI_1, "صحيح البخاري", "1")["cards"]
    assert len({(x["scholar"], x["book"], x["number"]) for x in shown}) == len(shown)


def test_sharh_and_tafseer_lookups():
    c = DorarClient(transport=_transport(), cache=False)
    sh = c.sharh_for(BUKHARI_1, "صحيح البخاري", "1")
    assert sh and sh["url"].startswith("https://dorar.net/hadith/explain/") and "قاعدةٌ مِن قواعدِ الإسلامِ" in sh["text"]
    t = c.tafseer_for(20, 92)
    assert t and t["url"] == "https://dorar.net/tafseer/20/12" and t["text"].startswith("غريب الكلمات:")


def test_extended_explanation_is_grounded_in_the_retrieved_sharh(monkeypatch):
    from app import llm as llm_mod
    from app.config import Settings
    from app.llm import LLMClient
    from app.main import app

    seen: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"explanation": "المعنى الإجمالي:\\\\nملخص"}'}}]})

    settings = Settings(_env_file=None, llm_provider="gemini", gemini_api_key="g", llm_fallbacks="")
    monkeypatch.setattr(llm_mod, "_client", LLMClient(settings, transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(dorar, "_client", DorarClient(transport=_transport(), cache=False))
    client = TestClient(app)
    body = {"lang": "ar", "mode": "extended", "state": "verified", "confidence": 95, "input_text": "إنما الأعمال بالنيات",
            "matched_text": BUKHARI_1, "collection": "bukhari", "number": "1", "ruling": {"grade_ar": "صحيح"}}
    out = client.post("/api/explain", json=body).json()
    assert out["explanation"].startswith("المعنى الإجمالي") and out["grounding"]["url"].startswith("https://dorar.net/hadith/explain/")
    sent = seen[0]
    assert "SUMMARISING THE PROVIDED SOURCE TEXT ONLY" in sent["messages"][0]["content"]
    assert "قاعدةٌ مِن قواعدِ الإسلامِ" in sent["messages"][1]["content"]  # the retrieved شرح was the input


def test_extended_explanation_without_a_source_returns_no_text(monkeypatch):
    from app import llm as llm_mod
    from app.config import Settings
    from app.llm import LLMClient
    from app.main import app

    settings = Settings(_env_file=None, llm_provider="gemini", gemini_api_key="g", llm_fallbacks="")
    never = httpx.MockTransport(lambda r: httpx.Response(500))
    monkeypatch.setattr(llm_mod, "_client", LLMClient(settings, transport=never))
    empty = httpx.MockTransport(lambda r: httpx.Response(200, text="<html></html>"))
    monkeypatch.setattr(dorar, "_client", DorarClient(transport=empty, cache=False))
    body = {"lang": "ar", "mode": "extended", "state": "verified", "confidence": 95, "input_text": "x",
            "matched_text": BUKHARI_1, "collection": "bukhari", "number": "1"}
    out = TestClient(app).post("/api/explain", json=body).json()
    assert out["explanation"] is None and out["reason"] == "no_source"
