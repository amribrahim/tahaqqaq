"""Run the circulated-texts benchmark (eval/circulated.jsonl) against the API.
Labels come from الدرر السنية; "contested" items are listed but not scored.
- authentic: right = confirmed (verified/partial) with an authentic grade; missed = uncertain/abstain;
  dangerous = shown as weak or fabricated.
- not authentic (weak, fabricated, not a hadith): right = flagged with its weak/fabricated ruling ("unreliable") or
  abstained (no attribution); closest-only = shown as the closest text, not attributed; dangerous = confirmed as authentic.
Usage: python -m eval.run_circulated [--api http://localhost:8000] [--out /tmp/circulated.md]"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
_WEAK = re.compile(r"ضعيف|موضوع|باطل|لا أصل|منكر|كذب|مكذوب|لا يصح|ليس بحديث|واه|Da'?if|Fabricated|False|No basis", re.I)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--out", default="/tmp/circulated.md")
    a = ap.parse_args()
    items = [json.loads(x) for x in (HERE / "circulated.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    rows = []
    with httpx.Client(base_url=a.api, timeout=120) as c:
        for it in items:
            j = c.post("/api/verify", json={"text": it["text"], "lang": "ar", "explain": False}).json()
            g = (j.get("grade") or {}).get("grade_ar", "")
            src = j.get("source") or {}
            state = j["state"]
            weak_shown = state == "unreliable" or (state in ("verified", "partial") and bool(_WEAK.search(g)))
            strong_shown = state in ("verified", "partial") and not weak_shown
            if it["label"] == "authentic":
                outcome = "right" if strong_shown else "dangerous" if weak_shown else "missed"
            elif it["label"] == "not_authentic":
                outcome = "right" if (weak_shown or state == "abstain") else "dangerous" if strong_shown else "closest-only"
            else:
                outcome = "not scored"
            rows.append((it, state, g, f"{src.get('book_ar', '')} {src.get('number', '')}".strip(), outcome))
    lines = ["| Text | الدرر السنية | Tool | Grade shown | Outcome |", "|---|---|---|---|---|"]
    for it, state, g, where, outcome in rows:
        lines.append(f"| {it['text']} | {it['dorar_ruling']} | {state} {where} | {g} | {outcome} |")
    def count(label: str, outcome: str) -> int:
        return sum(1 for it, *_r, o in rows if it["label"] == label and o == outcome)
    auth = sum(1 for it, *_ in rows if it["label"] == "authentic")
    weak = sum(1 for it, *_ in rows if it["label"] == "not_authentic")
    summary = [
        "", f"**Authentic ({auth})**: confirmed {count('authentic', 'right')}, missed {count('authentic', 'missed')}, "
        f"shown as weak {count('authentic', 'dangerous')}.",
        f"**Weak, fabricated or not a hadith ({weak})**: flagged or abstained {count('not_authentic', 'right')}, "
        f"closest text only {count('not_authentic', 'closest-only')}, confirmed as authentic {count('not_authentic', 'dangerous')}.",
        f"**Dangerous errors: {count('authentic', 'dangerous') + count('not_authentic', 'dangerous')} / {auth + weak}**.",
    ]
    Path(a.out).write_text("\n".join(lines + summary) + "\n", encoding="utf-8")
    print("\n".join(lines + summary))


if __name__ == "__main__":
    main()
