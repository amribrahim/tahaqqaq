"""The same hadith pasted as a full translation in another language (the narrator preamble and the story included),
as people share it from translated hadith sites. The translations are made once by a model from the published English
(cached in translated_paste.jsonl); the tool must confirm the same hadith (record or narration).
Usage: python -m eval.run_translated_paste [--api http://localhost:8000] [--n 10]"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx

from app import db, llm

HERE = Path(__file__).resolve().parent
CACHE = HERE / "translated_paste.jsonl"
LANGS = {"fr": "French", "id": "Indonesian", "ur": "Urdu", "tr": "Turkish"}
SYSTEM = 'Translate the hadith text faithfully and completely into {lang}, keeping the narrator line. Return JSON: {{"text": "..."}}'


def build(n: int) -> list[dict]:
    if CACHE.exists():
        return [json.loads(x) for x in CACHE.read_text(encoding="utf-8").splitlines() if x.strip()]
    with db.get_conn() as conn:
        rows = conn.execute("SELECT collection, number, text_en FROM texts WHERE collection IN ('bukhari','muslim') "
                            "AND length(text_en) BETWEEN 150 AND 900 AND text_en ILIKE 'narrated%%' "
                            "ORDER BY md5('paste' || number || collection) LIMIT %s", (n,)).fetchall()
    items = []
    for r in rows:
        for code, name in LANGS.items():
            out = None
            for wait in (0, 20, 45):
                time.sleep(wait or 2)
                out = llm.get_client().complete(SYSTEM.format(lang=name), r["text_en"], json_mode=True, max_tokens=1500)
                if out:
                    break
            if not out:
                continue
            try:
                items.append({"lang": code, "text": json.loads(out[0])["text"], "record": [r["collection"], r["number"]]})
            except (ValueError, KeyError):
                continue
    CACHE.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in items) + "\n", encoding="utf-8")
    return items


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--pause", type=float, default=6.0)
    a = ap.parse_args()
    items = build(a.n)
    by: dict[str, list[bool]] = {}
    wrong, misses = 0, []
    with httpx.Client(base_url=a.api, timeout=180) as c:
        for i, it in enumerate(items):
            time.sleep(a.pause)
            c.headers["x-forwarded-for"] = f"10.97.0.{i + 1}"
            j = c.post("/api/verify", json={"text": it["text"], "lang": "en", "explain": False}).json()
            src = j.get("source") or {}
            got = [src.get("collection"), src.get("number")]
            narr = [[n["collection"], n["number"]] for n in j.get("narrations") or []]
            hit = j["state"] in ("verified", "partial") and (got == it["record"] or it["record"] in narr)
            wrong += j["state"] in ("verified", "partial", "unreliable") and not hit
            by.setdefault(it["lang"], []).append(hit)
            if not hit:
                misses.append(f"- {it['lang']} {it['record']}: {j['state']} {j['confidence']} -> {got}")
    for lang, hits in by.items():
        print(f"{lang}: {sum(hits)}/{len(hits)}")
    print(f"all: {sum(sum(h) for h in by.values())}/{sum(len(h) for h in by.values())} · attributed to another hadith: {wrong}")
    print("\n".join(misses))


if __name__ == "__main__":
    main()
