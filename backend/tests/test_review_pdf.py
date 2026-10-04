"""Human-review PDF: only reports the server produced are rendered, links are unguessable and expire, and the PDF
carries the verdict, the requester and the source exactly as in the report."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import ratelimit, review_pdf
from app.main import app

client = TestClient(app)

REPORT = {
    "id": "srv123", "state": "verified", "confidence": 95, "reason_ar": "وُجد النص بلفظه.", "reason_en": "Found verbatim.",
    "input_text": "إنما الأعمال بالنيات", "created_at": "2026-10-04T10:20:00",
    "source": {"book_ar": "صحيح البخاري", "book_en": "Sahih al-Bukhari", "number": "1", "matn_ar": "إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ",
               "text_en": "Actions are but by intentions", "source_url": "https://dorar.net/hadith/sharh/1"},
    "grade": {"grade_ar": "صحيح", "grader_ar": "البخاري", "grade_en": "Sahih", "grader_en": "al-Bukhari"},
    "narrations": [{"book_ar": "صحيح مسلم", "book_en": "Sahih Muslim", "number": "1907a", "grade_ar": "صحيح", "grade_en": ""}],
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

    monkeypatch.setattr(review_pdf, "render_pdf", lambda rep, lang, name, email: f"PDF {rep['id']} {rep['state']} {name}".encode())
    monkeypatch.setattr(review_pdf, "save", save)
    monkeypatch.setattr(review_pdf, "load", stored.get)
    yield stored


def test_html_carries_verdict_requester_source_and_escapes():
    page = review_pdf.render_html({**REPORT, "input_text": "<script>x</script>"}, "ar", "عمرو", "a@b.co")
    for part in ("مؤيَّد بمصدر", "صحيح البخاري", "إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ", "البخاري", "عمرو", "a@b.co", "1907a", 'dir="rtl"'):
        assert part in page
    assert "<script>" not in page and "&lt;script&gt;" in page
    en = review_pdf.render_html(REPORT, "en", "Amr", "a@b.co")
    assert "Confirmed by source" in en and 'dir="ltr"' in en and "Sahih al-Bukhari" in en
    assert "1907a</span> — صحيح</li>" in en      # no English grade recorded: the Arabic ruling, verbatim


def test_uses_the_report_the_server_produced(_clean):
    review_pdf.remember(REPORT)
    j = client.post("/api/review/pdf", json={"report_id": "srv123", "text": "ignored", "lang": "ar", "name": "Amr", "email": "a@b.co"}).json()
    assert j["report_id"] == "srv123" and j["state"] == "verified" and j["retain_days"] == review_pdf.RETAIN_DAYS
    r = client.get(j["path"])
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content == b"PDF srv123 verified Amr"
    assert "noindex" in r.headers["x-robots-tag"]


def test_unknown_report_is_verified_again_from_its_text(monkeypatch):
    from app import pipeline

    calls = []

    class Fake:
        def model_dump(self):
            return {**REPORT, "id": "fresh1", "state": "partial"}

    monkeypatch.setattr(pipeline, "run", lambda text, lang, via, explain=True: calls.append((text, explain)) or Fake())
    j = client.post("/api/review/pdf", json={"report_id": "gone", "text": "إنما الأعمال", "lang": "ar", "name": "Amr", "email": "a@b.co"}).json()
    assert calls == [("إنما الأعمال", False)] and j["report_id"] == "fresh1" and j["state"] == "partial"


def test_rejects_bad_email_missing_name_and_bad_tokens():
    assert client.post("/api/review/pdf", json={"report_id": "x", "text": "t", "name": "Amr", "email": "not-an-email"}).status_code == 422
    assert client.post("/api/review/pdf", json={"report_id": "x", "text": "t", "name": "", "email": "a@b.co"}).status_code == 422
    assert client.get("/api/review/pdf/short").status_code == 404
    assert client.get("/api/review/pdf/" + "y" * 32).status_code == 404


def test_rate_limited():
    review_pdf.remember(REPORT)
    codes = [client.post("/api/review/pdf", json={"report_id": "srv123", "name": "A", "email": "a@b.co"},
                         headers={"x-forwarded-for": "10.9.9.9"}).status_code for _ in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429


def test_memory_is_bounded_and_expires(monkeypatch):
    for i in range(review_pdf.RECENT_MAX + 5):
        review_pdf.remember({"id": f"r{i}", "state": "abstain"})
    assert len(review_pdf._recent) == review_pdf.RECENT_MAX and review_pdf.recall("r0") is None
    t = __import__("time").time()
    monkeypatch.setattr(review_pdf.time, "time", lambda: t + review_pdf.RECENT_HOURS * 3600 + 1)
    assert review_pdf.recall(f"r{review_pdf.RECENT_MAX + 4}") is None


def test_real_pdf_when_pango_is_available():
    try:
        from weasyprint import HTML
    except (ImportError, OSError):
        pytest.skip("Pango not installed on this machine")
    pdf = HTML(string=review_pdf.render_html(REPORT, "ar", "عمرو", "a@b.co")).write_pdf()
    assert pdf[:5] == b"%PDF-" and len(pdf) > 5000
