"""normalize_ar: one key for typed / OCR / URL text and for ingested records."""
from __future__ import annotations

from app.normalize import normalize_ar

PLAIN = "انما الاعمال بالنيات وانما لكل امري ما نوي"


def test_tashkeel_honorific_and_quotes_collapse_to_plain():
    full = "قال رسول الله ﷺ: «إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ، وَإِنَّمَا لِكُلِّ امْرِئٍ مَا نَوَى» رواه البخاري"
    assert normalize_ar(full) == PLAIN
    assert normalize_ar("إنما الأعمال بالنيات وإنما لكل امرئ ما نوى") == PLAIN


def test_leadins_and_honorifics_everywhere():
    assert normalize_ar("عن عمر بن الخطاب رضي الله عنه قال: قال النبي صلى الله عليه وسلم: إنما الأعمال بالنيات وإنما لكل امرئ ما نوى") == PLAIN
    assert normalize_ar("حدثنا الحميدي قال حدثنا سفيان عن النبي صلى الله عليه وسلم قال إنما الأعمال بالنيات وإنما لكل امرئ ما نوى") == PLAIN
    assert normalize_ar("حديث شريف: \"إنما الأعمال بالنيات، وإنما لكل امرئ ما نوى\" (متفق عليه)") == PLAIN


def test_symbols_emoji_and_tatweel_are_dropped():
    assert normalize_ar("🤲 إنمـــا الأعمال بالنيّات ❤️ وإنما لكل امرئ ما نوى ✨") == PLAIN


def test_ocr_noise_variants_still_share_most_of_the_key():
    noisy = "قال رسول الله صلى عليه وسلم: «إنما الأعمال بالنيات. وإنما لكل امرئ ما نوى» رواه البخاري"
    assert normalize_ar(noisy) == PLAIN


def test_does_not_strip_a_saying_that_starts_with_a_leadin_word_only():
    # «قال» alone is a lead-in, but the saying itself must survive
    assert normalize_ar("قال: الدين النصيحة") == "الدين النصيحه"
    assert normalize_ar("إن الله جميل يحب الجمال") == "ان الله جميل يحب الجمال"
