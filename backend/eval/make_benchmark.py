"""Build the labelled benchmark (eval/benchmark.jsonl) from the ingested database, with a fixed seed.

Groups: sahih exact · sahih variants (tashkeel stripped, 1-2 typos, attribution + quotes) · curated
fabricated/weak sayings · ayat exact · ayat misquoted (one word changed) · invented texts · fatwa questions.
Usage: python -m eval.make_benchmark   (needs DATABASE_URL)"""
from __future__ import annotations

import json
import random
from pathlib import Path

from app import db
from app.normalize import strip_tashkeel

OUT = Path(__file__).resolve().parent / "benchmark.jsonl"
rng = random.Random(2026)

INVENTED = [
    "من قرأ هذا النص غُفر له كل ذنب",
    "من قرأ هذا الدعاء ونشره بين عشرة أشخاص فُرّج همّه في يومه",
    "من شرب القهوة بعد الفجر كُتب له أجر صيام يوم",
    "من قال سبحان الله مئة مرة يوم الخميس بُني له قصر في الجنة من ذهب",
    "إذا رأيتم الهلال في ليلة السبت فتصدقوا بخاتم من فضة",
    "من نام على جنبه الأيسر ليلة الجمعة رأى النبي في منامه",
]
FATWA = [
    "هل يجوز لي أن أفعل كذا في زواجي؟",
    "هل يجوز لي الجمع بين الصلاتين في السفر؟",
    "ما حكم بيع الذهب بالتقسيط؟",
    "نسيت ركعة في صلاة العصر فماذا أفعل؟",
    "هل علي كفارة إذا أفطرت في رمضان بسبب المرض؟",
]


def typo(word: str) -> str:
    """One realistic Arabic typo: drop a letter, swap two letters, or ta-marbuta/ha, ya/alef-maqsura."""
    if len(word) < 4:
        return word
    choice = rng.choice(["drop", "swap", "form"])
    if choice == "drop":
        i = rng.randrange(1, len(word) - 1)
        return word[:i] + word[i + 1 :]
    if choice == "swap":
        i = rng.randrange(1, len(word) - 1)
        return word[:i] + word[i + 1] + word[i] + word[i + 2 :]
    return word.replace("ة", "ه") if "ة" in word else word.replace("ى", "ي") if "ى" in word else word[:-1]


def variant(matn: str) -> str:
    words = strip_tashkeel(matn).replace("‏", "").split()
    for _ in range(rng.choice([1, 2])):
        i = rng.randrange(len(words))
        words[i] = typo(words[i])
    text = " ".join(words)
    return rng.choice([f"قال رسول الله ﷺ: «{text}»", f"قال النبي صلى الله عليه وسلم: {text}", f"«{text}» رواه البخاري", text])


def misquote(ayah: str) -> str:
    words = strip_tashkeel(ayah).split()
    i = rng.randrange(len(words))
    words[i] = typo(words[i]) if len(words[i]) >= 4 else words[i] + "ا"
    return " ".join(words)


def equivalents(conn, collection: str, number: str) -> list[list[str]]:
    """All records carrying the same normalised wording (the Six Books repeat many hadiths under several
    numbers and across books): any of them is a correct attribution."""
    rows = conn.execute(
        "SELECT t2.collection, t2.number FROM texts t1 JOIN texts t2 ON t2.matn_norm = t1.matn_norm "
        "WHERE t1.collection = %s AND t1.number = %s ORDER BY t2.collection, t2.number", (collection, number),
    ).fetchall()
    return [[r["collection"], r["number"]] for r in rows] or [[collection, number]]


def main() -> None:
    items: list[dict] = []
    with db.get_conn() as conn:
        sahih = conn.execute(
            "SELECT collection, number, matn_ar FROM texts WHERE collection IN ('bukhari','muslim') "
            "AND array_length(string_to_array(matn_norm, ' '), 1) BETWEEN 6 AND 30 ORDER BY md5(number || collection) LIMIT 60"
        ).fetchall()
        seeds = conn.execute("SELECT collection, number, matn_ar, grades FROM texts WHERE kind = 'seed' ORDER BY id").fetchall()
        ayat = conn.execute(
            "SELECT number, text_ar FROM texts WHERE kind = 'quran' AND array_length(string_to_array(matn_norm, ' '), 1) BETWEEN 5 AND 20 "
            "ORDER BY md5(number) LIMIT 15"
        ).fetchall()
        eq = {(r["collection"], r["number"]): equivalents(conn, r["collection"], r["number"]) for r in sahih}
    for r in sahih[:30]:
        items.append({"group": "sahih_exact", "text": strip_tashkeel(r["matn_ar"]), "expect_state": ["verified"],
                      "expect_record": eq[(r["collection"], r["number"])]})
    for r in sahih[30:60]:
        items.append({"group": "sahih_variant", "text": variant(r["matn_ar"]), "expect_state": ["verified", "partial"],
                      "expect_record": eq[(r["collection"], r["number"])]})
    for r in seeds:
        items.append({"group": "fabricated_or_weak", "text": r["matn_ar"], "expect_state": ["unreliable"],
                      "expect_record": [[r["collection"], r["number"]]], "expect_grade": r["grades"][0]["grade_ar"]})
    for r in ayat[:10]:
        items.append({"group": "ayah_exact", "text": strip_tashkeel(r["text_ar"]), "expect_state": ["verified"],
                      "expect_record": [["quran", r["number"]]]})
    for r in ayat[10:15]:
        items.append({"group": "ayah_misquoted", "text": misquote(r["text_ar"]), "expect_state": ["verified", "partial"],
                      "expect_record": [["quran", r["number"]]]})
    for t in INVENTED:
        items.append({"group": "invented", "text": t, "expect_state": ["abstain"], "expect_record": None})
    for t in FATWA:
        items.append({"group": "fatwa", "text": t, "expect_state": ["referral"], "expect_record": None})
    OUT.write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n", encoding="utf-8")
    print(f"wrote {len(items)} items to {OUT}")


if __name__ == "__main__":
    main()
