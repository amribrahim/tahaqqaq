"""Run the labelled benchmark against the running API and print a markdown report.

Usage: python -m eval.run_benchmark [--api http://localhost:8000] [--out ../qa/benchmark.md]
Metrics per group: accuracy (expected state AND expected record). Global: wrong-attribution rate
(a confirmed/partial/unreliable answer pointing at a record other than the expected one), abstain
precision (invented texts that abstained), and median latency."""
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
            grade_ok = ("expect_grade" not in it) or ((j.get("grade") or {}).get("grade_ar") == it["expect_grade"])
            attributed = j["state"] in ("verified", "partial", "unreliable")
            wrong_attr = attributed and it["expect_record"] is not None and got_rec not in it["expect_record"]
            wrong_attr = wrong_attr or (attributed and it["expect_record"] is None)
            rows.append({**it, "got_state": j["state"], "got_record": got_rec, "confidence": j["confidence"], "ms": ms,
                         "ok": state_ok and rec_ok and grade_ok, "wrong_attribution": wrong_attr})
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r["group"]].append(r)
    lines = ["# Benchmark — تحقّق", "", f"{len(rows)} labelled inputs, run against `{a.api}` with the optional AI steps off.", "",
             "Expected records include every record that carries the same wording (the Six Books repeat hadiths across numbers and books).", "",
             "| Group | n | Accuracy (state + record) | Wrong attributions |", "|---|---|---|---|"]
    for g, rs in groups.items():
        acc = sum(r["ok"] for r in rs) / len(rs)
        lines.append(f"| {g} | {len(rs)} | {acc:.0%} | {sum(r['wrong_attribution'] for r in rs)} |")
    total_ok = sum(r["ok"] for r in rows) / len(rows)
    wrong = sum(r["wrong_attribution"] for r in rows)
    inv = groups.get("invented", [])
    lines += ["", f"**Overall accuracy: {total_ok:.0%}** · **wrong attributions: {wrong} / {len(rows)}** "
              f"({wrong / len(rows):.1%}) · abstain on invented texts: {sum(r['got_state'] == 'abstain' for r in inv)}/{len(inv)} · "
              f"median latency {statistics.median(r['ms'] for r in rows)} ms", "", "## Misses", ""]
    misses = [r for r in rows if not r["ok"]]
    if not misses:
        lines.append("none")
    for r in misses:
        lines.append(f"- [{r['group']}] `{r['text'][:70]}` → got {r['got_state']} {r['got_record']} ({r['confidence']}%), expected {r['expect_state']} {r['expect_record']}")
    Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
