"""English pasted as sunnah.com shows it: the full published translation of a Bukhari or Muslim hadith, narrator
preamble and narrative included. The tool must confirm the same hadith (the record or one of its narrations).
Usage: python -m eval.run_english_paste [--api http://localhost:8000] [--n 40]"""
from __future__ import annotations

import argparse
import time

import httpx

from app import db


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--n", type=int, default=40)
    a = ap.parse_args()
    with db.get_conn() as conn:
        rows = conn.execute("SELECT collection, number, text_en FROM texts WHERE collection IN ('bukhari','muslim') "
                            "AND length(text_en) BETWEEN 150 AND 1500 AND text_en ILIKE 'narrated%%' "
                            "ORDER BY md5('paste' || number || collection) LIMIT %s", (a.n,)).fetchall()
    ok, misses = 0, []
    with httpx.Client(base_url=a.api, timeout=120) as c:
        for i, r in enumerate(rows):
            c.headers["x-forwarded-for"] = f"10.98.0.{i + 1}"
            j = c.post("/api/verify", json={"text": r["text_en"], "lang": "en", "explain": False}).json()
            src = j.get("source") or {}
            got = (src.get("collection"), src.get("number"))
            narr = {(n["collection"], n["number"]) for n in j.get("narrations") or []}
            hit = j["state"] in ("verified", "partial") and (got == (r["collection"], r["number"]) or (r["collection"], r["number"]) in narr)
            ok += hit
            if not hit:
                misses.append(f"- {r['collection']} {r['number']}: {j['state']} {j['confidence']} -> {got} | {r['text_en'][:70]}")
            time.sleep(0.3)
    print(f"Right hadith: {ok}/{len(rows)}")
    print("\n".join(misses))


if __name__ == "__main__":
    main()
