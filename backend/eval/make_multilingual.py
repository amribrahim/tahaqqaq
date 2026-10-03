"""Build the multilingual benchmark: authentic hadiths from the corpus, rendered by an LLM into other languages
as a user would type them (not a published translation). Each item is labelled with its source record.
Usage: python -m eval.make_multilingual  →  eval/multilingual.jsonl
The inputs are machine-written; the labels come from the corpus, not from the model."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from app import db, llm
from app.records import is_cross_reference

HERE = Path(__file__).resolve().parent
_EN_XREF = re.compile(r"above hadith|this hadith has been (?:reported|narrated|transmitted)|same chain|like this has been", re.I)
LANGS = {"fr": "French", "id": "Indonesian", "ur": "Urdu", "tr": "Turkish", "en": "English"}
SYSTEM = """Render a hadith the way an ordinary person would write it in a social-media post in the requested language:
natural wording, your own phrasing, NOT a published translation, no isnad, no reference, no quotation marks.
Return JSON: {"text": "<the hadith in that language>"}"""


def main() -> None:
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT collection, number, matn_ar, matn_norm, text_en FROM texts WHERE collection IN ('bukhari','muslim') "
            "AND array_length(string_to_array(matn_norm, ' '), 1) BETWEEN 8 AND 30 "
            "ORDER BY md5('multi' || number || collection) LIMIT 40").fetchall()
    # skip records with no text of their own, in Arabic («بمثله») or in English ("The above hadith has been ...")
    rows = [r for r in rows if not is_cross_reference(r["matn_norm"]) and not _EN_XREF.search(r["text_en"] or "")][:20]
    client = llm.get_client()
    path = HERE / "multilingual.jsonl"
    out = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []
    done = {(tuple(x["expect_record"][0]), x["lang"]) for x in out}
    for r in rows:
        for code, name in LANGS.items():
            if ((r["collection"], r["number"]), code) in done:
                continue
            res = None
            for wait in (0, 20, 45, 90):     # free tiers rate-limit: back off and retry
                time.sleep(wait or 2)
                res = client.complete(SYSTEM, f"Language: {name}\nHadith (Arabic): {r['matn_ar']}", json_mode=True, max_tokens=400)
                if res:
                    break
            if not res:
                print("skip", r["collection"], r["number"], code, flush=True)
                continue
            try:
                text = json.loads(res[0])["text"].strip()
            except (ValueError, KeyError, TypeError):
                continue
            out.append({"lang": code, "text": text, "expect_record": [[r["collection"], r["number"]]], "model": res[1]})
            print(code, r["collection"], r["number"], text[:70], flush=True)
    path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in out) + "\n", encoding="utf-8")
    print(len(out), "items")


if __name__ == "__main__":
    main()
