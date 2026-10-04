"""Human-review PDF: only reports the server produced are printed, the result page receives the report as is, links
are unguessable and expire. (The real print, a headless browser on the result page, runs in the browser tests.)"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import ratelimit, review_pdf
from app.main import app

client = TestClient(app)

REPORT = {
    "id": "srv123", "state": "verified", "confidence": 95, "reason_ar": "وُجد النص بلفظه.", "reason_en": "Found verbatim.",
    "input_text": "إنما الأعمال بالنيات", "created_at": "2026-10-04T10:20:00",
    "source": {"book_ar": "صحيح البخاري", "book_en": "Sahih al-Bukhari", "number": "1"},
}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    ratelimit.reset()
    review_pdf._recent.clear()
    stored: dict[str, tuple[bytes, str]] = {}

    def save(pdf: bytes, report_id: str) -> str:
        token = f"tok_{len(stored):02d}_" + "x" * 30
        stored[token] = (pdf, report_id)
        return token

    monkeypatch.setattr(review_pdf, "render_pdf", lambda rep, lang, tz="": f"PDF {rep['id']} {rep['state']} {lang} {tz}".encode())
    monkeypatch.setattr(review_pdf, "save", save)
    monkeypatch.setattr(review_pdf, "load", stored.get)
    yield stored


def test_the_result_page_receives_the_report_as_is():
    url, script = review_pdf.page_setup(REPORT, "ar")
    assert url.endswith("/result/?id=srv123")
    key = "tahqaq.report.srv123"
    assert f'sessionStorage.setItem("{key}", ' in script and "localStorage.setItem('tahqaq.lang', \"ar\")" in script
    stored = json.loads(json.loads(script.split(f'"{key}", ', 1)[1].split(");localStorage", 1)[0]))
    assert stored == {**REPORT, "server_id": "srv123"}


def test_prints_the_report_the_server_produced():
    review_pdf.remember(REPORT)
    j = client.post("/api/review/pdf", json={"report_id": "srv123", "text": "ignored", "lang": "en", "tz": "Africa/Cairo"}).json()
    assert j["report_id"] == "srv123" and j["state"] == "verified" and j["retain_days"] == review_pdf.RETAIN_DAYS
    r = client.get(j["path"])
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content == b"PDF srv123 verified en Africa/Cairo"
    assert "noindex" in r.headers["x-robots-tag"]


def test_unknown_report_is_verified_again_from_its_text(monkeypatch):
    from app import pipeline

    calls = []

    class Fake:
        def model_dump(self):
            return {**REPORT, "id": "fresh1", "state": "partial"}

    monkeypatch.setattr(pipeline, "run", lambda text, lang, via, explain=True: calls.append((text, explain)) or Fake())
    j = client.post("/api/review/pdf", json={"report_id": "gone", "text": "إنما الأعمال", "lang": "ar"}).json()
    assert calls == [("إنما الأعمال", False)] and j["report_id"] == "fresh1" and j["state"] == "partial"


def test_name_and_email_never_reach_the_server_and_bad_tokens_are_404():
    from app.schemas import ReviewPdfRequest

    assert not {"name", "email"} & set(ReviewPdfRequest.model_fields)
    assert client.get("/api/review/pdf/short").status_code == 404
    assert client.get("/api/review/pdf/" + "y" * 32).status_code == 404


def test_rate_limited():
    review_pdf.remember(REPORT)
    codes = [client.post("/api/review/pdf", json={"report_id": "srv123"}, headers={"x-forwarded-for": "10.9.9.9"}).status_code
             for _ in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429


def test_time_zone_is_the_persons_when_valid():
    assert review_pdf.time_zone("Africa/Cairo") == "Africa/Cairo"
    assert review_pdf.time_zone("") == review_pdf.time_zone("Not/AZone") == review_pdf.time_zone("../etc") == "Asia/Riyadh"


def test_memory_is_bounded_and_expires(monkeypatch):
    for i in range(review_pdf.RECENT_MAX + 5):
        review_pdf.remember({"id": f"r{i}", "state": "abstain"})
    assert len(review_pdf._recent) == review_pdf.RECENT_MAX and review_pdf.recall("r0") is None
    t = __import__("time").time()
    monkeypatch.setattr(review_pdf.time, "time", lambda: t + review_pdf.RECENT_HOURS * 3600 + 1)
    assert review_pdf.recall(f"r{review_pdf.RECENT_MAX + 4}") is None
