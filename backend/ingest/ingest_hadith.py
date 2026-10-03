"""Ingest the Six Books from the open hadith-api dataset (fawazahmed0/hadith-api, CC0).

Each record keeps: full Arabic text, extracted matn, the published English translation and the
scholars' gradings VERBATIM (`grades` array from the dataset, e.g. Al-Albani / Shuaib Al Arnaut).
Bukhari and Muslim carry no per-hadith grade in the dataset; the compiler's own inclusion is the
ruling there (as dorar.net records it: المحدث: البخاري · المصدر: صحيح البخاري · [صحيح]).

Usage: python -m ingest.ingest_hadith [--books bukhari,muslim,...] [--limit N]
"""
from __future__ import annotations

import argparse
import re

from app.normalize import extract_matn, normalize_ar, normalize_latin
from app.translation import quoted_part
from ingest.common import CDN, dorar_url, embed_chunks, ensure_schema, fetch_json, log, upsert_records

BOOKS: dict[str, dict] = {
    "bukhari": {"ar": "صحيح البخاري", "en": "Sahih al-Bukhari", "sunnah": "bukhari", "compiler_ar": "البخاري", "compiler_en": "Al-Bukhari"},
    "muslim": {"ar": "صحيح مسلم", "en": "Sahih Muslim", "sunnah": "muslim", "compiler_ar": "مسلم", "compiler_en": "Muslim"},
    "abudawud": {"ar": "سنن أبي داود", "en": "Sunan Abi Dawud", "sunnah": "abudawud"},
    "tirmidhi": {"ar": "جامع الترمذي", "en": "Jami' al-Tirmidhi", "sunnah": "tirmidhi"},
    "nasai": {"ar": "سنن النسائي", "en": "Sunan al-Nasa'i", "sunnah": "nasai"},
    "ibnmajah": {"ar": "سنن ابن ماجه", "en": "Sunan Ibn Majah", "sunnah": "ibnmajah"},
    # optional, behind --books
    "malik": {"ar": "موطأ مالك", "en": "Muwatta Malik", "sunnah": "malik"},
}
DEFAULT_BOOKS = ["bukhari", "muslim", "abudawud", "tirmidhi", "nasai", "ibnmajah"]

GRADER_AR = {
    "Al-Albani": "الألباني", "Shuaib Al Arnaut": "شعيب الأرناؤوط", "Zubair Ali Zai": "زبير علي زئي",
    "Muhammad Muhyi Al-Din Abdul Hamid": "محمد محيي الدين عبد الحميد", "Ahmad Muhammad Shakir": "أحمد محمد شاكر",
    "Abu Ghuddah": "عبد الفتاح أبو غدة", "Darussalam": "دار السلام", "Salim al-Hilali": "سليم الهلالي",
    "Muhammad Fuad Abd al-Baqi": "محمد فؤاد عبد الباقي", "Ibn Hajar": "ابن حجر",
}
GRADE_AR = [
    ("Hasan Sahih", "حسن صحيح"), ("Sahih Lighairihi", "صحيح لغيره"), ("Hasan Lighairihi", "حسن لغيره"),
    ("Sahih Isnaad", "إسناده صحيح"), ("Isnaad Sahih", "إسناده صحيح"), ("Hasan Isnaad", "إسناده حسن"),
    ("Isnaad Hasan", "إسناده حسن"), ("Daif Jiddan", "ضعيف جدًا"), ("Da'if Jiddan", "ضعيف جدًا"),
    ("Sahih", "صحيح"), ("Hasan", "حسن"), ("Da'if", "ضعيف"), ("Daif", "ضعيف"), ("Mawdu", "موضوع"),
    ("Munkar", "منكر"), ("Shadh", "شاذ"), ("Maqtu", "مقطوع"), ("Mawquf", "موقوف"), ("Batil", "باطل"),
]


def grade_to_ar(g: str) -> str:
    s = g.strip()
    for en, ar in GRADE_AR:
        if s.lower() == en.lower():
            return ar
    out = s
    for en, ar in GRADE_AR:  # phrase-level fallback, longest first
        out = re.sub(re.escape(en), ar, out, flags=re.IGNORECASE)
    return out


def build_grades(book: str, raw: list[dict], number: str) -> list[dict]:
    info = BOOKS[book]
    grades = []
    for g in raw or []:
        name, grade = (g.get("name") or "").strip(), (g.get("grade") or "").strip()
        if not grade:
            continue
        grades.append({
            "grader_ar": GRADER_AR.get(name, name), "grader_en": name,
            "grade_ar": grade_to_ar(grade), "grade_en": grade,
            "source_ar": info["ar"], "source_en": info["en"], "number": number, "url": "",
        })
    if not grades and "compiler_ar" in info:
        grades.append({
            "grader_ar": info["compiler_ar"], "grader_en": info["compiler_en"],
            "grade_ar": "صحيح", "grade_en": "Sahih",
            "source_ar": info["ar"], "source_en": info["en"], "number": number, "url": "",
        })
    # Al-Albani first when present (the grader users expect for the Sunan)
    grades.sort(key=lambda g: 0 if g["grader_en"] == "Al-Albani" else 1)
    return grades


def display_number(book: str, h: dict) -> str:
    """Sahih Muslim: the dataset's `hadithnumber` is sequential; `arabicnumber` carries the
    Muhammad Fuad Abd al-Baqi number with the sub-narration as decimals ('8.02' -> '8b'),
    which is also the sunnah.com id. Other books: hadithnumber == arabicnumber."""
    raw = str(h.get("arabicnumber") or h["hadithnumber"])
    if book == "muslim" and "." in raw:
        whole, frac = raw.split(".", 1)
        try:
            sub = int(frac)
        except ValueError:
            return raw
        return whole + (chr(ord("a") + sub - 1) if sub >= 1 else "")
    return raw


def load_book(book: str, limit: int | None) -> list[dict]:
    info = BOOKS[book]
    ar = fetch_json(f"{CDN}/ara-{book}.min.json", f"ara-{book}.json")
    en = fetch_json(f"{CDN}/eng-{book}.min.json", f"eng-{book}.json")
    sections = ar.get("metadata", {}).get("sections", {}) or {}
    sections_en = en.get("metadata", {}).get("sections", {}) or {}
    en_by_num = {h["hadithnumber"]: h for h in en.get("hadiths", [])}
    rows = []
    seen: set[str] = set()
    for h in ar["hadiths"]:
        text = (h.get("text") or "").strip()
        if not text:
            continue
        num = display_number(book, h)
        if num in seen:
            num = f"{num}-{h['hadithnumber']}"
        seen.add(num)
        matn = extract_matn(text)
        sec = str((h.get("reference") or {}).get("book", ""))
        eh = en_by_num.get(h["hadithnumber"], {})
        rows.append({
            "kind": "hadith", "collection": book, "book_ar": info["ar"], "book_en": info["en"], "number": num,
            "chapter_ar": sections.get(sec, "") or "", "chapter_en": sections_en.get(sec, "") or "",
            "text_ar": text, "matn_ar": matn, "text_en": (eh.get("text") or "").strip(),
            "type_ar": "حديث نبوي", "type_en": "Prophetic hadith",
            "grades": build_grades(book, h.get("grades"), num),
            "source_url": dorar_url(matn),
            "alt_url": f"https://sunnah.com/{info['sunnah']}:{num}",
            "meta": {"arabicnumber": h.get("arabicnumber"), "hadithnumber": h["hadithnumber"], "section": sec},
        })
        if limit and len(rows) >= limit:
            break
    return rows


def run(books: list[str], limit: int | None) -> None:
    ensure_schema()
    for book in books:
        log(f"[hadith] {book}")
        rows = load_book(book, limit)
        log(f"  {len(rows)} hadiths; embedding Arabic matn windows…")
        ch_ar = embed_chunks([normalize_ar(r["matn_ar"]) for r in rows], "ar")
        log("  embedding English translation windows…")
        ch_en = embed_chunks([normalize_latin(quoted_part(r["text_en"])) for r in rows], "en")
        for i, r in enumerate(rows):
            r["chunks_ar"], r["chunks_en"] = ch_ar[i], ch_en[i]
        upsert_records(rows)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--books", default=",".join(DEFAULT_BOOKS))
    p.add_argument("--limit", type=int, default=None, help="per-book cap (dev only)")
    a = p.parse_args()
    run([b.strip() for b in a.books.split(",") if b.strip()], a.limit)
