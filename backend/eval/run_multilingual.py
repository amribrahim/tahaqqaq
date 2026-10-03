"""Run the multilingual benchmark against the API. An item is correct when the report confirms (verified/partial)
the labelled hadith: the labelled record, a reviewed parallel narration of it (multilingual_equivalents.json), or a
record whose narrations (same text in another book/number) include it.
Usage: python -m eval.run_multilingual [--api http://localhost:8000] [--out /tmp/multilingual.md] [--save rows.json]"""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent


def verify(c: httpx.Client, text: str) -> dict:
    for wait in (0, 20, 45, 90):   # other-language input needs the LLM translation step; free tiers rate-limit
        time.sleep(wait or 1)
        j = c.post("/api/verify", json={"text": text, "lang": "en", "explain": False}).json()
        if not (j["state"] == "abstain" and "Arabic or English" in (j.get("reason_en") or "")):
            return j
    return j


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--out", default="/tmp/multilingual.md")
    ap.add_argument("--save", default="")
    a = ap.parse_args()
    items = [json.loads(x) for x in (HERE / "multilingual.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    equiv = {k: v for k, v in json.loads((HERE / "multilingual_equivalents.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}
    rows = []
    with httpx.Client(base_url=a.api, timeout=180) as c:
        for it in items:
            j = verify(c, it["text"])
            src = j.get("source") or {}
            got = [src.get("collection"), src.get("number")] if src else None
            narr = [[n["collection"], n["number"]] for n in j.get("narrations") or []]
            label = it["expect_record"][0]
            accepted = [label] + [x.split(" ", 1) for x in equiv.get(f"{label[0]} {label[1]}", [])]
            hit = got in accepted or any(e in narr for e in accepted)
            ok = j["state"] in ("verified", "partial") and hit
            wrong = j["state"] in ("verified", "partial", "unreliable") and not hit
            rows.append({**it, "state": j["state"], "got": got, "confidence": j["confidence"], "ok": ok, "wrong": wrong,
                         "mt": (j.get("machine_translation") or {}).get("english", "")})
    by = defaultdict(list)
    for r in rows:
        by[r["lang"]].append(r)
    lines = ["| Language | n | Confirmed the right hadith | Abstained or uncertain | Attributed to another hadith |", "|---|---|---|---|---|"]
    for lang, rs in by.items():
        lines.append(f"| {lang} | {len(rs)} | {sum(r['ok'] for r in rs) / len(rs):.0%} | "
                     f"{sum(r['state'] in ('abstain', 'uncertain') for r in rs)} | {sum(r['wrong'] for r in rs)} |")
    lines.append(f"| **all** | {len(rows)} | **{sum(r['ok'] for r in rows) / len(rows):.0%}** | "
                 f"{sum(r['state'] in ('abstain', 'uncertain') for r in rows)} | {sum(r['wrong'] for r in rows)} |")
    Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    if a.save:
        Path(a.save).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
