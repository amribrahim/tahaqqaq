"""Test fixtures: an in-memory store seeded with a small, representative slice of the data
(a few Bukhari/Muslim hadiths with their English translations, the curated rulings seed, a few
ayat and the glossary). Uses the real local embedding model so semantic matching is exercised;
set EMBEDDER=hash for a fast offline smoke run."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("EMBEDDER", "local")
os.environ.setdefault("ANTHROPIC_API_KEY", "")  # the LLM must never be needed for a verdict

from app.embeddings import get_embedder
from app.normalize import extract_matn, normalize_ar, normalize_latin  # noqa: E402
from app.records import GlossaryTerm, Record
from app.store import MemoryStore, set_store

SEEDS = Path(__file__).resolve().parent.parent / "ingest" / "seeds"

HADITHS = [
    # (collection, book_ar, book_en, number, chapter_ar, text_ar, text_en, grades)
    ("bukhari", "صحيح البخاري", "Sahih al-Bukhari", "1", "كتاب بدء الوحي",
     "حَدَّثَنَا الْحُمَيْدِيُّ عَبْدُ اللَّهِ بْنُ الزُّبَيْرِ، قَالَ حَدَّثَنَا سُفْيَانُ، عَنْ عُمَرَ بْنِ الْخَطَّابِ ـ رضى الله عنه ـ عَلَى الْمِنْبَرِ قَالَ سَمِعْتُ رَسُولَ اللَّهِ صلى الله عليه وسلم يَقُولُ ‏\"‏ إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ، وَإِنَّمَا لِكُلِّ امْرِئٍ مَا نَوَى، فَمَنْ كَانَتْ هِجْرَتُهُ إِلَى دُنْيَا يُصِيبُهَا أَوْ إِلَى امْرَأَةٍ يَنْكِحُهَا فَهِجْرَتُهُ إِلَى مَا هَاجَرَ إِلَيْهِ ‏\"‏‏.‏",
     "I heard Allah's Messenger (ﷺ) saying, \"The reward of deeds depends upon the intentions and every person will get the reward according to what he has intended.\"",
     [{"grader_ar": "البخاري", "grader_en": "Al-Bukhari", "grade_ar": "صحيح", "grade_en": "Sahih", "source_ar": "صحيح البخاري", "source_en": "Sahih al-Bukhari", "number": "1"}]),
    ("bukhari", "صحيح البخاري", "Sahih al-Bukhari", "13", "كتاب الإيمان",
     "عَنْ أَنَسٍ عَنِ النَّبِيِّ صلى الله عليه وسلم قَالَ ‏\"‏ لاَ يُؤْمِنُ أَحَدُكُمْ حَتَّى يُحِبَّ لأَخِيهِ مَا يُحِبُّ لِنَفْسِهِ ‏\"‏‏.‏",
     "The Prophet (ﷺ) said, \"None of you will have faith till he wishes for his (Muslim) brother what he likes for himself.\"",
     [{"grader_ar": "البخاري", "grader_en": "Al-Bukhari", "grade_ar": "صحيح", "grade_en": "Sahih", "source_ar": "صحيح البخاري", "source_en": "Sahih al-Bukhari", "number": "13"}]),
    ("muslim", "صحيح مسلم", "Sahih Muslim", "223", "كتاب الطهارة",
     "عَنْ أَبِي مَالِكٍ الأَشْعَرِيِّ قَالَ قَالَ رَسُولُ اللَّهِ صلى الله عليه وسلم ‏\"‏ الطُّهُورُ شَطْرُ الإِيمَانِ وَالْحَمْدُ لِلَّهِ تَمْلأُ الْمِيزَانَ ‏\"‏",
     "The Messenger of Allah (ﷺ) said: Cleanliness is half of faith and al-Hamdu Lillah fills the scale.",
     [{"grader_ar": "مسلم", "grader_en": "Muslim", "grade_ar": "صحيح", "grade_en": "Sahih", "source_ar": "صحيح مسلم", "source_en": "Sahih Muslim", "number": "223"}]),
    ("muslim", "صحيح مسلم", "Sahih Muslim", "2699", "كتاب الذكر",
     "عَنْ أَبِي هُرَيْرَةَ قَالَ قَالَ رَسُولُ اللَّهِ صلى الله عليه وسلم ‏\"‏ مَنْ نَفَّسَ عَنْ مُؤْمِنٍ كُرْبَةً مِنْ كُرَبِ الدُّنْيَا نَفَّسَ اللَّهُ عَنْهُ كُرْبَةً مِنْ كُرَبِ يَوْمِ الْقِيَامَةِ ‏\"‏",
     "He who alleviates the suffering of a brother out of the sufferings of the world, Allah would alleviate his suffering from the sufferings of the Day of Resurrection.",
     [{"grader_ar": "مسلم", "grader_en": "Muslim", "grade_ar": "صحيح", "grade_en": "Sahih", "source_ar": "صحيح مسلم", "source_en": "Sahih Muslim", "number": "2699"}]),
    ("tirmidhi", "جامع الترمذي", "Jami' al-Tirmidhi", "2517", "كتاب صفة القيامة",
     "عَنْ أَنَسِ بْنِ مَالِكٍ قَالَ قَالَ رَجُلٌ يَا رَسُولَ اللَّهِ أَعْقِلُهَا وَأَتَوَكَّلُ أَوْ أُطْلِقُهَا وَأَتَوَكَّلُ قَالَ ‏\"‏ اعْقِلْهَا وَتَوَكَّلْ ‏\"‏",
     "A man said: O Messenger of Allah, shall I tie it and rely, or leave it loose and rely? He said: Tie it and rely.",
     [{"grader_ar": "الألباني", "grader_en": "Al-Albani", "grade_ar": "حسن", "grade_en": "Hasan", "source_ar": "جامع الترمذي", "source_en": "Jami' al-Tirmidhi", "number": "2517"}]),
    # a Sunan hadith with NO recorded ruling -> must never be attributed as verified
    ("ibnmajah", "سنن ابن ماجه", "Sunan Ibn Majah", "9999", "كتاب الزهد",
     "عَنْ فُلاَنٍ عَنِ النَّبِيِّ صلى الله عليه وسلم قَالَ ‏\"‏ الدُّنْيَا دَارُ مَنْ لاَ دَارَ لَهُ وَلَهَا يَجْمَعُ مَنْ لاَ عَقْلَ لَهُ ‏\"‏",
     "", []),
]

AYAT = [
    ("20:114", "سورة طه", "Surah Taha", "وَقُل رَّبِّ زِدْنِي عِلْمًا", "and say, 'My Lord, increase me in knowledge.'"),
    ("2:255", "سورة البقرة", "Surah Al-Baqarah", "ٱللَّهُ لَآ إِلَـٰهَ إِلَّا هُوَ ٱلْحَىُّ ٱلْقَيُّومُ ۚ لَا تَأْخُذُهُۥ سِنَةٌ وَلَا نَوْمٌ", "Allah - there is no deity except Him, the Ever-Living, the Sustainer of existence. Neither drowsiness overtakes Him nor sleep."),
    ("65:3", "سورة الطلاق", "Surah At-Talaq", "وَمَن يَتَوَكَّلْ عَلَى ٱللَّهِ فَهُوَ حَسْبُهُۥٓ", "And whoever relies upon Allah - then He is sufficient for him."),
]


def _records() -> list[Record]:
    recs: list[Record] = []
    i = 0
    for col, bar, ben, num, ch, text, en, grades in HADITHS:
        i += 1
        matn = extract_matn(text)
        recs.append(Record(id=i, kind="hadith", collection=col, book_ar=bar, book_en=ben, number=num, chapter_ar=ch,
                           chapter_en="", text_ar=text, matn_ar=matn, matn_norm=normalize_ar(matn), text_en=en,
                           text_en_norm=normalize_latin(en), type_ar="حديث نبوي", type_en="Prophetic hadith", grades=grades,
                           source_url=f"https://dorar.net/hadith/search?q={num}", alt_url=f"https://sunnah.com/{col}:{num}"))
    for key, sar, sen, text, en in AYAT:
        i += 1
        plain = normalize_ar(text)
        recs.append(Record(id=i, kind="quran", collection="quran", book_ar="القرآن الكريم", book_en="The Qur'an", number=key,
                           chapter_ar=sar, chapter_en=sen, text_ar=text, matn_ar=text, matn_norm=plain, text_en=en,
                           text_en_norm=normalize_latin(en), type_ar="آية", type_en="Qur'anic verse",
                           grades=[{"grader_ar": "مصحف المدينة", "grader_en": "Madinah Mushaf", "grade_ar": "آية قرآنية", "grade_en": "Qur'anic verse",
                                    "source_ar": sar, "source_en": sen, "number": key}],
                           source_url=f"https://quran.com/{key.replace(':', '/')}"))
    seed = json.loads((SEEDS / "rulings_seed.json").read_text(encoding="utf-8"))["items"]
    for n, it in enumerate(seed, 1):
        i += 1
        g0 = it["grades"][0]
        recs.append(Record(id=i, kind="seed", collection="seed", book_ar=g0["source_ar"], book_en=g0["source_en"], number=str(n),
                           chapter_ar=it.get("note_ar", ""), chapter_en=it.get("note_en", ""), text_ar=it["text_ar"],
                           matn_ar=it["text_ar"], matn_norm=normalize_ar(it["text_ar"]), text_en=it.get("text_en", ""),
                           text_en_norm=normalize_latin(it.get("text_en", "")), type_ar=it["type_ar"], type_en=it["type_en"],
                           grades=it["grades"], source_url="https://dorar.net/hadith/search?q=seed"))
    return recs


def _glossary() -> list[GlossaryTerm]:
    with (SEEDS / "glossary.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [GlossaryTerm(term_ar=r["term_ar"], term_en=r["term_en"], meaning_en=r["meaning_en"], meaning_ar=r["meaning_ar"],
                         avoid=[a for a in r["avoid"].split(";") if a], note_ar=r["note_ar"], note_en=r["note_en"],
                         source_url=r["source_url"]) for r in rows]


@pytest.fixture(scope="session", autouse=True)
def memory_store():
    store = MemoryStore.build(_records(), _glossary(), get_embedder())
    set_store(store)
    yield store
    set_store(None)
