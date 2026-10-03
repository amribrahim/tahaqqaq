"""Qur'an translation and links aligned with the challenge's reference table:
  - English translation: Hilali & Khan, «The Noble Qur'an», printed by مجمع الملك فهد لطباعة المصحف الشريف
    (served by the QuranEnc API, key `english_hilali_khan`),
  - every verse links to quranpedia.net (الموسوعة القرآنية); quran.com stays as a secondary link.
The Arabic text itself is the Madinah Mushaf (KFGQPC Hafs) Uthmani text already ingested.

Usage: python -m ingest.quran_kfgqpc      (updates the existing Qur'an rows and re-embeds their English windows)"""
from __future__ import annotations

import json
import re

import httpx
from psycopg.types.json import Jsonb

from app import db
from app.translation import english_key
from ingest.common import DATA_DIR, embed_chunks, log

QURANENC = "https://quranenc.com/api/v1/translation/sura/english_hilali_khan/{s}"
QURANPEDIA = "https://quranpedia.net/surah/1/{s}/{a}"
GRADER_AR = "مصحف المدينة النبوية — مجمع الملك فهد"
GRADER_EN = "Madinah Mushaf — King Fahd Complex"


def load_translation() -> dict[str, str]:
    path = DATA_DIR / "quran-hilali-khan.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    with httpx.Client(timeout=60, headers={"User-Agent": "Tahaqqaq/0.1"}) as c:
        for s in range(1, 115):
            rows = c.get(QURANENC.format(s=s)).raise_for_status().json()["result"]
            for r in rows:
                t = re.sub(r"^\s*\d+\.\s*", "", r["translation"]).strip()
                out[f"{int(r['sura'])}:{int(r['aya'])}"] = t
            if s % 20 == 0:
                log(f"  translation: {s}/114 surahs")
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def run() -> None:
    tr = load_translation()
    log(f"[quran_kfgqpc] {len(tr)} verses translated")
    with db.get_conn() as conn:
        rows = conn.execute("SELECT id, number, grades FROM texts WHERE kind = 'quran' ORDER BY id").fetchall()
    updates = []
    for r in rows:
        s, a = (int(x) for x in r["number"].split(":"))
        en = tr.get(f"{s}:{a}", "")
        url = QURANPEDIA.format(s=s, a=a)
        grades = r["grades"] or [{}]
        for g in grades:
            g.update({"grader_ar": GRADER_AR, "grader_en": GRADER_EN, "url": url})
        updates.append((en, english_key(en, "quran"), url, f"https://quran.com/{s}/{a}", Jsonb(grades), r["id"]))
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany("UPDATE texts SET text_en=%s, text_en_norm=%s, source_url=%s, alt_url=%s, grades=%s WHERE id=%s", updates)
    log("  rows updated; re-embedding English windows of the verses")
    ids = [u[5] for u in updates]
    keys = [u[1] for u in updates]
    for i in range(0, len(ids), 2000):
        bi, bk = ids[i : i + 2000], keys[i : i + 2000]
        ch = embed_chunks(bk, "en")
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM chunks WHERE lang = 'en' AND text_id = ANY(%s)", (bi,))
                cur.executemany("INSERT INTO chunks (text_id, lang, pos, embedding) VALUES (%s, 'en', %s, %s)",
                                [(tid, pos, v) for tid, c in zip(bi, ch, strict=True) for pos, v in enumerate(c)])
    with db.get_conn() as conn:
        conn.execute("INSERT INTO ingest_meta (key, value) VALUES ('quran_translation', 'english_hilali_khan (KFGQPC) via quranenc') "
                     "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value")
    log("[quran_kfgqpc] done")


if __name__ == "__main__":
    run()
