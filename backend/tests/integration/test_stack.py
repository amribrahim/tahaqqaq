"""Integration checks against the running docker-compose stack.

Run with:  TAHQAQ_STACK=1 pytest tests/integration -q
Skipped automatically when the stack is not configured."""
from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

API = os.environ.get("TAHQAQ_API", "http://localhost:8000")
FIX = Path(__file__).resolve().parents[3] / "qa" / "fixtures" / "images"
pytestmark = pytest.mark.skipif(not os.environ.get("TAHQAQ_STACK"), reason="needs the running stack")


@pytest.fixture(scope="module")
def c():
    with httpx.Client(base_url=API, timeout=90) as client:
        yield client


def verify(c, **body):
    return c.post("/api/verify", json={"lang": "ar", "explain": False, **body})


def test_health(c):
    r = c.get("/health")
    assert r.status_code == 200
    j = r.json()
    assert j["db"] is True and j["counts"]["hadith"] > 30000 and j["counts"]["quran"] == 6236


@pytest.mark.parametrize("text,state,grade", [
    ("إنما الأعمال بالنيات", "verified", "صحيح"),
    ("إنما الاعمال بالنيه وانما لكل امرء ما نوى فمن كانت هجرته", "verified|partial", "صحيح"),
    ("حب الوطن من الإيمان", "unreliable", "موضوع"),
    ("صوموا تصحوا", "unreliable", "ضعيف"),
    ("من قرأ هذا النص غُفر له كل ذنب", "abstain|uncertain", None),
    ("هل يجوز لي أن أفعل كذا في زواجي؟", "referral", None),
])
def test_text_states(c, text, state, grade):
    r = verify(c, text=text)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["state"] in state.split("|"), j["reason_en"]
    if grade:
        assert j["grade"]["grade_ar"] == grade
        assert j["grade"]["grader_ar"]
        assert j["source"]["source_url"].startswith("https://dorar.net/hadith")
    else:
        if j["state"] == "abstain" or j["state"] == "referral":
            assert j["grade"] is None and j["source"] is None


def test_ayah_as_hadith(c):
    j = verify(c, text="قال رسول الله: وقل رب زدني علما").json()
    assert j["source"]["kind"] == "quran" and j["source"]["number"] == "20:114" and j["quran_note"]


def test_misquoted_ayah_has_diff(c):
    j = verify(c, text="وقل ربي زدني علما").json()
    assert j["source"]["number"] == "20:114"
    assert any(t["k"] != "eq" for t in j["diff_input"] + j["diff_source"])


def test_english_translation_card(c):
    j = verify(c, text="Actions are judged by intentions and every person will get what he intended", lang="en").json()
    assert j["input_lang"] == "en" and j["source"] and j["translation"]
    j = verify(c, text="None of you is a Muslim until he loves for his brother what he loves for himself.", lang="en").json()
    assert j["translation"]["issues"]


@pytest.mark.parametrize("text,code", [("", 400), ("   ", 400), ("ا" * 2001, 413)])
def test_validation(c, text, code):
    assert verify(c, text=text).status_code == code


@pytest.mark.parametrize("text", ["😀😀😀 🙏", "asdkjh qwe zxcv mnb", "hello مرحبا 123 😀", "<script>alert(1)</script>", "'; DROP TABLE texts; --"])
def test_weird_inputs_never_5xx(c, text):
    r = verify(c, text=text)
    assert r.status_code < 500, r.text


def test_image_ocr_paths(c):
    r = c.post("/api/ocr", files={"image": ("ar.png", (FIX / "ar.png").read_bytes(), "image/png")})
    assert r.status_code == 200 and "الأعمال" in r.json()["full"]
    # the OCR'd post verifies like the plain hadith text (same source, near-identical confidence)
    j = verify(c, text=r.json()["text"]).json()
    assert j["state"] == "verified" and j["source"]["collection"] == "bukhari" and j["source"]["number"] == "1"
    assert j["confidence"] >= 90
    # the comparison is made on the quoted saying, not on the attribution around it
    assert "صلى" not in "".join(t["t"] for t in j["diff_input"])
    r = c.post("/api/ocr", files={"image": ("en.png", (FIX / "en.png").read_bytes(), "image/png")})
    assert r.status_code == 200 and "Muslim" in r.json()["full"]
    r = c.post("/api/ocr", files={"image": ("ar-blurry.png", (FIX / "ar-blurry.png").read_bytes(), "image/png")})
    assert r.status_code in (200, 422)
    assert c.post("/api/ocr", files={"image": ("x.txt", b"not an image", "text/plain")}).status_code == 415
    assert c.post("/api/ocr", files={"image": ("empty.png", b"", "image/png")}).status_code == 422
    assert c.post("/api/ocr", files={"image": ("big.png", b"\0" * (11 * 1024 * 1024), "image/png")}).status_code == 413


@pytest.mark.parametrize("url,code", [
    ("http://fixtures/hadith.html", 200),
    ("http://fixtures/empty.html", 422),
    ("http://fixtures/loop1", 422),
    ("http://nonexistent.invalid/page", 422),
    ("ftp://example.com/x", 422),
    ("javascript:alert(1)", 422),
])
def test_url_paths(c, url, code):
    r = verify(c, url=url, explain=False)
    assert r.status_code == code, r.text
    if code == 200:
        j = r.json()
        assert j["source"]["number"] == "1" and j["source"]["collection"] == "bukhari"


def test_no_user_input_stored():
    import psycopg

    dsn = os.environ.get("DATABASE_URL", "postgresql://tahqaq:tahqaq@localhost:5432/tahqaq")
    with psycopg.connect(dsn) as conn:
        tables = {r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")}
        assert tables == {"texts", "chunks", "glossary", "ingest_meta", "source_cache"}
        # the reference cache is keyed by source wording only: no user text can be in it
        cached = conn.execute("SELECT count(*) FROM source_cache WHERE payload::text LIKE '%لا يُحفظ%' OR key LIKE '%لا يحفظ%'").fetchone()[0]
        assert cached == 0
        n = conn.execute("SELECT count(*) FROM texts").fetchone()[0]
    with httpx.Client(base_url=API, timeout=60) as c:
        c.post("/api/verify", json={"text": "نص اختبار لا يُحفظ"})
        c.post("/api/review", json={"report_id": "x", "text": "نص اختبار لا يُحفظ", "state": "abstain"})
    with psycopg.connect(dsn) as conn:
        assert conn.execute("SELECT count(*) FROM texts").fetchone()[0] == n
        assert conn.execute("SELECT count(*) FROM texts WHERE text_ar LIKE '%لا يُحفظ%'").fetchone()[0] == 0


# ---- spec item 7: fixture pages and the OCR image resolve like typed text -----------------------

FIXTURE_PAGES = [
    ("http://fixtures/hadith.html", "bukhari", "1", "verified"),
    ("http://fixtures/blockquote.html", "muslim", "223", "verified|partial"),
    ("http://fixtures/ayah.html", "quran", "20:114", "verified|partial"),
    ("http://fixtures/weak.html", "seed", None, "unreliable"),
    ("http://fixtures/multi.html", "bukhari", "1", "verified"),
    ("http://fixtures/noisy.html", "bukhari", "13", "verified|partial"),
]


@pytest.mark.parametrize("url,collection,number,state", FIXTURE_PAGES)
def test_fixture_pages_resolve_like_typed_text(c, url, collection, number, state):
    r = verify(c, url=url, explain=False)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["state"] in state.split("|"), (url, j["reason_en"])
    assert j["source"]["collection"] == collection, j["source"]
    if number:
        assert j["source"]["number"] == number
    if url.endswith("ayah.html"):
        assert j["quran_note"]
    if url.endswith("multi.html"):
        # the second quoted hadith on the page is listed under nearest results
        assert any(cd["collection"] == "muslim" and cd["number"] == "223" for cd in j["candidates"]), [
            (cd["book_ar"], cd["number"]) for cd in j["candidates"]]


def test_png_and_typed_text_resolve_to_the_same_record(c):
    typed = verify(c, text="إنما الأعمال بالنيات وإنما لكل امرئ ما نوى", explain=False).json()
    r = c.post("/api/ocr", files={"image": ("ar.png", (FIX / "ar.png").read_bytes(), "image/png")})
    assert r.status_code == 200
    from_png = verify(c, text=r.json()["full"], explain=False).json()
    assert (typed["source"]["collection"], typed["source"]["number"]) == (from_png["source"]["collection"], from_png["source"]["number"]) == ("bukhari", "1")
    assert typed["state"] == from_png["state"] == "verified"


@pytest.mark.parametrize("ai", ["0", "1"])
def test_sunnah_screenshot_full_transcription_and_verdict(c, ai):
    """A sunnah.com screenshot (isnad + matn, vocalised, coloured narrator names): the review text must be the
    whole transcription (start of the chain AND end of the matn), and verifying it must give Bukhari 1."""
    img = (FIX / "sunnah-bukhari1.png").read_bytes()
    r = c.post("/api/ocr", files={"image": ("sunnah.png", img, "image/png")}, data={"ai": ai})
    assert r.status_code == 200, r.text
    text = r.json()["text"]
    from app.normalize import normalize_ar

    key = normalize_ar(text, strip_leadins=False)
    assert "سفيان" in key and "هاجر اليه" in key, text  # nothing was cut away
    j = verify(c, text=text, via="image").json()
    assert j["state"] in (("verified",) if ai == "1" else ("verified", "partial")), j["reason_en"]
    assert j["source"]["collection"] == "bukhari"


def test_dorar_rulings_for_a_matched_hadith(c):
    j = c.get("/api/dorar", params={"collection": "bukhari", "number": "1"}).json()
    if not j["available"]:
        pytest.skip(f"dorar.net unreachable from the stack: {j.get('reason')}")
    assert j["best"]["book"] == "صحيح البخاري" and "صحيح" in j["best"]["grade"]
    assert j["search_url"].startswith("https://dorar.net/hadith/search")
    assert c.get("/api/dorar", params={"collection": "quran", "number": "20:114"}).json()["available"] is False


def test_quran_rows_use_the_kfgqpc_translation_and_quranpedia(c):
    j = verify(c, text="وقل رب زدني علما").json()
    assert j["source"]["source_url"] == "https://quranpedia.net/surah/1/20/114"
    assert "Increase me in knowledge" in j["source"]["text_en"]  # Hilali & Khan wording
