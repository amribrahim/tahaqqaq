"""Ingest the Qur'an (Uthmani script of the Madina Mushaf, King Fahd Complex standard) via the
open Quran.com v4 API, with the Saheeh International translation as the approved English text.

Usage: python -m ingest.ingest_quran
"""
from __future__ import annotations

import httpx

from app.normalize import normalize_ar, normalize_latin, strip_tashkeel
from app.translation import quoted_part
from ingest.common import DATA_DIR, embed_chunks, ensure_schema, fetch_json, log, upsert_records

API = "https://api.quran.com/api/v4"
SAHEEH_INTERNATIONAL = 131


def load_chapters() -> dict[int, dict]:
    d = fetch_json(f"{API}/chapters?language=en", "quran-chapters.json")
    return {c["id"]: c for c in d["chapters"]}


def load_verses() -> list[dict]:
    d = fetch_json(f"{API}/quran/verses/uthmani", "quran-uthmani.json")
    return d["verses"]


def load_translation() -> dict[str, str]:
    path = DATA_DIR / "quran-saheeh.json"
    if not path.exists():
        log("  downloading Saheeh International translation (page by page)…")
        out: dict[str, str] = {}
        with httpx.Client(timeout=120) as c:
            page = 1
            while True:
                r = c.get(f"{API}/quran/translations/{SAHEEH_INTERNATIONAL}", params={"page": page, "per_page": 1000})
                r.raise_for_status()
                data = r.json()
                for t in data["translations"]:
                    out[str(t["resource_id"]) + ":" + str(t.get("verse_key") or t.get("verse_id"))] = t["text"]
                pag = data.get("pagination") or {}
                if not pag.get("next_page"):
                    break
                page = pag["next_page"]
        import json

        path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def run() -> None:
    ensure_schema()
    log("[quran] loading")
    chapters = load_chapters()
    verses = load_verses()
    tr = load_translation()
    # the translations endpoint returns verse_id-ordered rows; map by verse id order
    tr_by_id = {}
    for k, v in tr.items():
        tr_by_id[k.split(":", 1)[1]] = v
    import re

    rows = []
    for v in verses:
        key = v["verse_key"]
        surah, ayah = key.split(":")
        ch = chapters[int(surah)]
        text = v["text_uthmani"]
        plain = strip_tashkeel(text)
        en = tr_by_id.get(str(v["id"])) or tr_by_id.get(key) or ""
        en = re.sub(r"<sup[^>]*>.*?</sup>", "", en)
        rows.append({
            "kind": "quran", "collection": "quran", "book_ar": "القرآن الكريم", "book_en": "The Qur'an",
            "number": key, "chapter_ar": f"سورة {ch['name_arabic']}", "chapter_en": f"Surah {ch['name_simple']}",
            "text_ar": text, "matn_ar": plain, "text_en": en, "type_ar": "آية", "type_en": "Qur'anic verse",
            "grades": [{
                "grader_ar": "مصحف المدينة النبوية — مجمع الملك فهد", "grader_en": "Madinah Mushaf — King Fahd Complex",
                "grade_ar": "آية قرآنية", "grade_en": "Qur'anic verse",
                "source_ar": f"سورة {ch['name_arabic']}", "source_en": f"Surah {ch['name_simple']}",
                "number": f"{surah}:{ayah}", "url": f"https://quran.com/{surah}/{ayah}",
            }],
            "source_url": f"https://quran.com/{surah}/{ayah}",
            "alt_url": f"https://quranenc.com/en/browse/arabic_moyassar/{surah}/{ayah}",
            "meta": {"surah": int(surah), "ayah": int(ayah), "surah_ar": ch["name_arabic"], "surah_en": ch["name_simple"]},
        })
    log(f"  {len(rows)} verses; embedding…")
    ch_ar = embed_chunks([normalize_ar(r["matn_ar"]) for r in rows], "ar")
    ch_en = embed_chunks([normalize_latin(quoted_part(r["text_en"] or "")) for r in rows], "en")
    for i, r in enumerate(rows):
        r["chunks_ar"], r["chunks_en"] = ch_ar[i], ch_en[i]
    upsert_records(rows)


if __name__ == "__main__":
    run()
