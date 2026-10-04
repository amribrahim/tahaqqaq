"""Grow the curated seed of circulated sayings from الدرر السنية (dorar.net, the approved hadith reference).

For every line of ingest/seeds/circulated_candidates.txt the الدرر search is fetched (cached in source_cache) and the
result cards whose wording matches the saying are read. A saying is ADDED only when:
  - at least one matching card records a weak, fabricated or baseless ruling, and
  - no matching card records an authentic ruling (صحيح / حسن / ثابت), so contested sayings stay out.
The rulings are copied verbatim (grade, scholar, book, number) with the الدرر search link. Nothing is generated.
The decisions are written to ingest/seeds/seed_review.md for a specialist to review before launch.

Usage: python -m ingest.build_seed_from_dorar [--dry-run]"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from rapidfuzz import fuzz

from app.dorar import DorarClient
from app.normalize import normalize_ar

SEEDS = Path(__file__).resolve().parent / "seeds"
CANDIDATES = SEEDS / "circulated_candidates.txt"
SEED = SEEDS / "rulings_seed.json"
REVIEW = SEEDS / "seed_review.md"

_WEAK = re.compile(r"ضعيف|ضعف|موضوع|باطل|لا أصل|لا اصل|منكر|كذب|مكذوب|لم أجده|لم يرد|لا يصح|لم يصح|لا يثبت|لم يثبت|ليس بحديث|"
                   r"ليس حديثا|ليس بثابت|ليس بصحيح|واه|متروك|كذاب|وضاع|هالك|غير صحيح|لا يعرف له إسناد")
_STRONG = re.compile(r"صحيح|حسن|جيد|ثابت|أخرجه البخاري|أخرجه مسلم|متفق عليه")
# «ليس له إسناد ثابت», «لم يأت من طريق صحيح», «معناه صحيح لكن…»: the word for authentic appears only negated
_NEGATED = re.compile(r"(?:ليس|لا|لم|غير|ما)\s[^،.؛]{0,30}?(?:صحيح|ثابت|حسن|يصح|يثبت)|"
                      r"لم يجدوا له أصلا|لا يعرف له أصل|تالف|شبه الريح|مجمع على ضعف|معناه صحيح|صحيح المعنى|صحيح من حيث المعنى")
# Descriptions of the narrators, not a ruling on the text: neither authentic nor weak
_NEUTRAL = re.compile(r"رجال الصحيح|رجاله ثقات|رجاله رجال|على شرط الصحيح|بعضها على شرط")
STRONG_SIM = 70   # an authentic ruling blocks a saying even when its wording is only close (variant wordings)
VARIANT_SIM = 80  # the second, looser search: a variant wording must still be this close to block


def grade_class(g: str) -> str:
    """weak | strong | neutral for one verbatim ruling."""
    if _WEAK.search(g) or _NEGATED.search(g):
        return "weak"
    if _STRONG.search(_NEUTRAL.sub(" ", g)):
        return "strong"
    return "neutral"
WEAK_SIM = 85     # a weak ruling must match the saying closely to be quoted for it
# Who is shown first when several scholars ruled on the same saying
_PREFERRED = ["الألباني", "ابن الجوزي", "ابن تيمية", "الذهبي", "السخاوي", "السيوطي", "ابن باز", "ابن عثيمين", "الصغاني",
              "الشوكاني", "ملا علي قاري", "العراقي", "ابن حجر العسقلاني", "النووي"]

GRADER_EN = {
    "الألباني": "Al-Albani", "ابن الجوزي": "Ibn al-Jawzi", "السخاوي": "Al-Sakhawi", "السيوطي": "Al-Suyuti",
    "ابن تيمية": "Ibn Taymiyyah", "الذهبي": "Al-Dhahabi", "ابن باز": "Ibn Baz", "ابن عثيمين": "Ibn Uthaymin",
    "العراقي": "Al-Iraqi", "الصغاني": "Al-Saghani", "الشوكاني": "Al-Shawkani", "ملا علي قاري": "Mulla Ali al-Qari",
    "الزرقاني": "Al-Zurqani", "العجلوني": "Al-Ajluni", "ابن حجر العسقلاني": "Ibn Hajar al-Asqalani", "النووي": "Al-Nawawi",
    "ابن القيم": "Ibn al-Qayyim", "الهيثمي": "Al-Haythami", "ابن عدي": "Ibn Adi", "العقيلي": "Al-Uqayli",
    "ابن حبان": "Ibn Hibban", "البيهقي": "Al-Bayhaqi", "الدارقطني": "Al-Daraqutni", "شعيب الأرناؤوط": "Shu'ayb al-Arna'ut",
    "الوادعي": "Al-Wadi'i", "ابن القيسراني": "Ibn al-Qaysarani", "ابن عبدالبر": "Ibn Abd al-Barr", "المنذري": "Al-Mundhiri",
    "السمهودي": "Al-Samhudi", "القاوقجي": "Al-Qawuqji", "الفتني": "Al-Fattani", "الزيلعي": "Al-Zayla'i",
    "الصنعاني": "Al-San'ani", "زين الدين المناوي": "Al-Munawi", "صدر الدين المناوي": "Al-Munawi", "ابن كثير": "Ibn Kathir",
    "ابن رجب": "Ibn Rajab", "ابن عراق الكناني": "Ibn Arraq", "الإمام أحمد": "Imam Ahmad", "يحيى بن معين": "Yahya ibn Ma'in",
    "أبو حاتم الرازي": "Abu Hatim al-Razi", "محمد جار الله الصعدي": "Al-Sa'di", "ابن همات الدمشقي": "Ibn Hammat al-Dimashqi",
    "ابن عساكر": "Ibn Asakir", "الطبراني": "Al-Tabarani", "ابن عبد الهادي": "Ibn Abd al-Hadi", "السفاريني الحنبلي": "Al-Saffarini",
}
SOURCE_EN = {
    "السلسلة الضعيفة": "Al-Silsilah al-Da'ifah", "ضعيف الجامع": "Da'if al-Jami'", "ضعيف الترغيب": "Da'if al-Targhib",
    "الموضوعات لابن الجوزي": "Al-Mawdu'at (Ibn al-Jawzi)", "الموضوعات للصغاني": "Al-Mawdu'at (al-Saghani)",
    "المقاصد الحسنة": "Al-Maqasid al-Hasanah", "كشف الخفاء": "Kashf al-Khafa'", "الأسرار المرفوعة": "Al-Asrar al-Marfu'ah",
    "الفوائد المجموعة": "Al-Fawa'id al-Majmu'ah", "مجموع الفتاوى": "Majmu' al-Fatawa", "تخريج الإحياء للعراقي": "Takhrij al-Ihya'",
    "مختصر المقاصد": "Mukhtasar al-Maqasid", "الجامع الصغير": "Al-Jami' al-Saghir", "تذكرة الموضوعات": "Tadhkirat al-Mawdu'at",
    "اللؤلؤ المرصوع": "Al-Lu'lu' al-Marsu'", "المنار المنيف": "Al-Manar al-Munif", "ميزان الاعتدال": "Mizan al-I'tidal",
    "مجمع الزوائد": "Majma' al-Zawa'id", "الكامل في الضعفاء": "Al-Kamil fi al-Du'afa'", "المجروحين": "Al-Majruhin",
    "ضعيف ابن ماجه": "Da'if Ibn Majah", "ضعيف الترمذي": "Da'if al-Tirmidhi", "ضعيف أبي داود": "Da'if Abi Dawud",
    "ضعيف النسائي": "Da'if al-Nasa'i", "مجموع فتاوى ابن باز": "Majmu' Fatawa Ibn Baz", "فيض القدير": "Fayd al-Qadir",
}
GRADE_EN = [  # first match wins; the Arabic grade is always shown verbatim
    (r"ليس بحديث|ليس حديثا", "Not a hadith"), (r"لا أصل|لا اصل|لم يرد|لم أجده", "No basis"), (r"موضوع|مكذوب|كذب", "Fabricated (mawdu')"),
    (r"باطل", "False (batil)"), (r"منكر", "Denounced (munkar)"), (r"ضعيف جد|واه|هالك|متروك", "Very weak"),
    (r"ضعيف", "Weak (da'if)"), (r"لا يصح|لم يصح|لا يثبت|لم يثبت|ليس بثابت|غير صحيح|ليس بصحيح", "Not authentic"),
]


def _grade_en(g: str) -> str:
    return next((en for pat, en in GRADE_EN if re.search(pat, g)), "Not authentic (see the Arabic ruling)")


def _clean(s: str) -> str:
    return re.sub(r"^\[|\]$", "", (s or "").strip()).strip()


def _number(n: str) -> str:
    return (n or "").split("/")[-1].strip() if re.fullmatch(r"[\d/ ]+", (n or "").strip()) else (n or "").strip()


def decide(candidate: str, cards: list[dict]) -> tuple[str, str, list[dict]]:
    """(decision, reason, matching cards): decision is add | skip."""
    key = normalize_ar(candidate)
    sim = {id(c): fuzz.partial_ratio(key, normalize_ar(c["text"])) for c in cards if c.get("text")}
    near = [c for c in cards if sim.get(id(c), 0) >= STRONG_SIM]
    close = [c for c in near if sim[id(c)] >= WEAK_SIM]
    if not close:
        return "skip", "no matching entry in الدرر", []

    weak = [c for c in close if grade_class(c["grade"]) == "weak"]
    strong = [c for c in near if grade_class(c["grade"]) == "strong"]
    if strong:
        return "skip", f"an authentic ruling exists ({_clean(strong[0]['grade'])} — {strong[0]['scholar']})", close
    if not weak:
        return "skip", "no clear weak or fabricated ruling among the matching entries", close
    return "add", f"{len(weak)} matching entries record a weak or fabricated ruling", weak


def variant_blocker(client: DorarClient, candidate: str) -> str:
    """Ask الدرر for rulings of authenticity only (its d[]=1 filter), on the full wording and on the first and last
    words («استعينوا … بالكتمان») to reach variant wordings. Any close entry graded authentic blocks the saying:
    a contested saying is never added as weak. Returns a description of the blocker, or ""."""
    key = normalize_ar(candidate)
    words = candidate.split()
    queries = [candidate] + ([f"{words[0]} {words[-1]}"] if len(words) >= 3 else [])
    for q in queries:
        # الدرر's authentic-only filter, then the plain search (some authentic rulings, e.g. «إسناده حسن», sit outside it)
        for c in client.search_authentic(q, words=10):
            if c.get("text") and fuzz.partial_ratio(key, normalize_ar(c["text"])) >= VARIANT_SIM and grade_class(c.get("grade", "")) != "weak":
                return f"{_clean(c['grade'])} — {c['scholar']}: {c['text'][:60]}"
        for c in client.search(q, words=10):
            if c.get("text") and fuzz.partial_ratio(key, normalize_ar(c["text"])) >= VARIANT_SIM and grade_class(c.get("grade", "")) == "strong":
                return f"{_clean(c['grade'])} — {c['scholar']}: {c['text'][:60]}"
    return ""


def to_grades(weak: list[dict], url: str) -> list[dict]:
    order = {name: i for i, name in enumerate(_PREFERRED)}
    seen, out = set(), []
    for c in sorted(weak, key=lambda c: order.get(c["scholar"], 99)):
        k = (c["scholar"], c["book"])
        if k in seen:
            continue
        seen.add(k)
        g = _clean(c["grade"])
        out.append({"grader_ar": c["scholar"], "grader_en": GRADER_EN.get(c["scholar"], c["scholar"]),
                    "grade_ar": g, "grade_en": _grade_en(g), "source_ar": c["book"],
                    "source_en": SOURCE_EN.get(c["book"], c["book"]), "number": _number(c.get("number", "")), "url": url})
        if len(out) == 3:
            break
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    existing = seed["items"]
    have = [normalize_ar(it["text_ar"]) for it in existing]
    client = DorarClient()
    lines = [x.strip() for x in CANDIDATES.read_text(encoding="utf-8").splitlines() if x.strip() and not x.startswith("#")]
    review = ["# Seed review — circulated sayings labelled from الدرر السنية", "",
              "Each saying below was searched on dorar.net. **add** means: a matching entry records a weak, fabricated or",
              "baseless ruling and no matching entry records an authentic one. The rulings are quoted verbatim. To be reviewed",
              "by a hadith specialist before a public launch.", "",
              "| Saying | Decision | Reason | Rulings quoted from الدرر |", "|---|---|---|---|"]
    added = 0
    for text in lines:
        key = normalize_ar(text)
        if any(fuzz.ratio(key, h) >= 90 for h in have):
            review.append(f"| {text} | already in the seed | — | — |")
            continue
        cards = client.search(text, words=10)
        decision, reason, used = decide(text, cards)
        if decision == "add":
            blocker = variant_blocker(client, text)
            if blocker:
                decision, reason = "skip", f"an authentic ruling exists for a variant wording ({blocker})"
        url = client.search_url(text, 10)
        quoted = "<br>".join(f"{_clean(c['grade'])} — {c['scholar']}، {c['book']} {c.get('number', '')}".strip() for c in used[:3])
        review.append(f"| {text} | {decision} | {reason} | {quoted or '—'} |")
        if decision == "add":
            existing.append({
                "text_ar": text, "text_en": "",
                "type_ar": "قول منتشر منسوب إلى النبي ﷺ", "type_en": "Circulated saying attributed to the Prophet ﷺ",
                "grades": to_grades(used, url), "dorar_text": used[0]["text"], "source": "dorar",
            })
            have.append(key)
            added += 1
        time.sleep(0.5)
    review += ["", f"Added {added} sayings; the seed now holds {len(existing)}."]
    REVIEW.write_text("\n".join(review) + "\n", encoding="utf-8")
    if not a.dry_run:
        seed["items"] = existing
        seed["_note"] = ("Curated seed of widely circulated sayings that are NOT in the Six Books, with the scholars' rulings as "
                         "recorded on dorar.net (الموسوعة الحديثية), copied verbatim. Items with \"source\": \"dorar\" were added by "
                         "ingest/build_seed_from_dorar.py (decisions in seed_review.md). Every entry must be reviewed by a "
                         "specialist before launch.")
        SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"added {added}; seed now {len(existing)}; review in {REVIEW}")


if __name__ == "__main__":
    main()
