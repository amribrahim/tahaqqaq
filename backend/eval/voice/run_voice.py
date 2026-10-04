"""Run the voice benchmark: each recording goes to /api/stt (Whisper on Groq); accepted transcripts go to /api/verify.
Reports the word error rate of the transcription, the share of recordings that lead to the right hadith (labelled
record or one of its narrations), and whether every negative recording got the expected refusal.
Usage: python -m eval.voice.run_voice [--api http://localhost:8000] [--labels eval/voice/voice.jsonl] [--audio qa/voice]"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import httpx

from app.normalize import normalize_ar, normalize_latin

HERE = Path(__file__).resolve().parent


def wer(ref: str, hyp: str) -> float:
    r, h = ref.split(), hyp.split()
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)] / max(1, len(r))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--labels", default=str(HERE / "voice.jsonl"))
    ap.add_argument("--audio", default=str(HERE.parents[2] / "qa" / "voice"))
    ap.add_argument("--pause", type=float, default=3.0)
    a = ap.parse_args()
    items = [json.loads(x) for x in Path(a.labels).read_text(encoding="utf-8").splitlines() if x.strip()]
    rows = []
    with httpx.Client(base_url=a.api, timeout=120) as c:
        for k, it in enumerate(items):
            time.sleep(a.pause)
            # run directly against the API (no proxy): a distinct client address per item keeps the per-user limit of the
            # assistant from throttling the benchmark (behind Caddy this header is set from the real client)
            c.headers["x-forwarded-for"] = f"10.99.0.{k + 1}"
            path = Path(a.audio) / it["file"]
            mime = "audio/mp4" if path.suffix == ".m4a" else "audio/wav"
            r = c.post("/api/stt", files={"audio": (path.name, path.read_bytes(), mime)}, data={"lang": "ar"})
            body = r.json()
            if "expect_error" in it:
                code = (body.get("detail") or {}).get("code") if r.status_code != 200 else None
                rows.append({**it, "ok": bool(code) and code in it["expect_error"].split("|"), "got": code or body.get("text")})
                continue
            if r.status_code != 200:
                rows.append({**it, "ok": False, "got": (body.get("detail") or {}).get("code"), "wer": 1.0})
                continue
            norm = normalize_ar if it["lang"] == "ar" else normalize_latin
            w = wer(norm(it["text"]), norm(body["text"]))
            v = c.post("/api/verify", json={"text": body["text"], "lang": it["lang"], "explain": False}).json()
            src = v.get("source") or {}
            got = [src.get("collection"), src.get("number")]
            narr = [[n["collection"], n["number"]] for n in v.get("narrations") or []]
            right = v["state"] in ("verified", "partial") and (got in it["expect_record"] or any(e in narr for e in it["expect_record"]))
            rows.append({**it, "ok": right, "wer": w, "state": v["state"], "got": got, "transcript": body["text"], "confidence": body["confidence"]})
    pos = [r for r in rows if "expect_error" not in r]
    neg = [r for r in rows if "expect_error" in r]
    lines = ["| Set | n | Right hadith | Median word error rate | Mean word error rate |", "|---|---|---|---|---|"]
    for lang in ("ar", "en"):
        rs = [r for r in pos if r["lang"] == lang]
        if rs:
            lines.append(f"| {lang} | {len(rs)} | {sum(r['ok'] for r in rs)}/{len(rs)} | {statistics.median(r['wer'] for r in rs):.0%} | "
                         f"{statistics.mean(r['wer'] for r in rs):.0%} |")
    lines.append(f"| refusals (silence, French, noise) | {len(neg)} | {sum(r['ok'] for r in neg)}/{len(neg)} refused correctly | — | — |")
    misses = [f"- {r['file']}: {r.get('state', '')} {r.get('got')} | {r.get('transcript', '')[:80]}" for r in rows if not r["ok"]]
    print("\n".join(lines + ["", "Misses:"] + (misses or ["none"])))


if __name__ == "__main__":
    main()
