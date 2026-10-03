"""Run the labelled benchmark against the running API and print a markdown report.

Usage: python -m eval.run_benchmark [--api http://localhost:8000] [--out ../qa/benchmark.md]
Metrics per group: accuracy (expected state AND expected record). Two record rules are reported:
- strict: the returned record is one of the labelled records;
- same hadith: the returned record is labelled, OR a labelled record is listed among the returned record's
  narrations (the same text in another book or under another number, shown to the user in the report).
Global: wrong attributions under both rules, abstain precision (invented texts that abstained), median latency."""
from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import defaultdict
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--out", default=str(HERE.parents[1] / "qa" / "benchmark.md"))
    a = ap.parse_args()
    items = [json.loads(line) for line in (HERE / "benchmark.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    rows: list[dict] = []
    with httpx.Client(base_url=a.api, timeout=120) as c:
        for it in items:
            t0 = time.perf_counter()
            r = c.post("/api/verify", json={"text": it["text"], "lang": "ar", "explain": False})
            ms = int((time.perf_counter() - t0) * 1000)
            j = r.json()
            src = j.get("source") or {}
            got_rec = [src.get("collection"), src.get("number")] if src else None
            state_ok = j["state"] in it["expect_state"]
            rec_ok = (it["expect_record"] is None) or (got_rec in it["expect_record"])
            narr = [[n["collection"], n["number"]] for n in j.get("narrations") or []]
            same_ok = rec_ok or (it["expect_record"] is not None and any(e in narr for e in it["expect_record"]))
            grade_ok = ("expect_grade" not in it) or ((j.get("grade") or {}).get("grade_ar") == it["expect_grade"])
            attributed = j["state"] in ("verified", "partial", "unreliable")
            wrong_attr = attributed and it["expect_record"] is not None and got_rec not in it["expect_record"]
            wrong_attr = wrong_attr or (attributed and it["expect_record"] is None)
            wrong_other = wrong_attr and not (attributed and same_ok and it["expect_record"] is not None)
            rows.append({**it, "got_state": j["state"], "got_record": got_rec, "confidence": j["confidence"], "ms": ms,
                         "ok": state_ok and rec_ok and grade_ok, "ok_same": state_ok and same_ok and grade_ok,
                         "wrong_attribution": wrong_attr, "wrong_other_hadith": wrong_other})
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r["group"]].append(r)
    lines = ["# Benchmark — تحقّق", "", f"{len(rows)} labelled inputs, run against `{a.api}` with the optional AI steps off.", "",
             "Expected records include every record that carries the same wording (the Six Books repeat hadiths across numbers and books).", "",
             "| Group | n | Accuracy, strict | Accuracy, same hadith | Wrong attributions, strict | Attributed to another hadith |",
             "|---|---|---|---|---|---|"]
    for g, rs in groups.items():
        acc = sum(r["ok"] for r in rs) / len(rs)
        acc2 = sum(r["ok_same"] for r in rs) / len(rs)
        lines.append(f"| {g} | {len(rs)} | {acc:.0%} | {acc2:.0%} | {sum(r['wrong_attribution'] for r in rs)} | {sum(r['wrong_other_hadith'] for r in rs)} |")
    total_ok = sum(r["ok"] for r in rows) / len(rows)
    total_same = sum(r["ok_same"] for r in rows) / len(rows)
    wrong = sum(r["wrong_attribution"] for r in rows)
    wrong_other = sum(r["wrong_other_hadith"] for r in rows)
    inv = groups.get("invented", [])
    lines += ["", f"**Accuracy: {total_ok:.0%} strict, {total_same:.0%} same hadith** · **wrong attributions: {wrong} / {len(rows)} strict, "
              f"{wrong_other} to another hadith** · abstain on invented texts: {sum(r['got_state'] == 'abstain' for r in inv)}/{len(inv)} · "
              f"median latency {statistics.median(r['ms'] for r in rows)} ms", "", "## Misses (same-hadith rule)", ""]
    misses = [r for r in rows if not r["ok_same"]]
    if not misses:
        lines.append("none")
    for r in misses:
        lines.append(f"- [{r['group']}] `{r['text'][:70]}` → got {r['got_state']} {r['got_record']} ({r['confidence']}%), expected {r['expect_state']} {r['expect_record']}")
    Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
