"""Build the "circulated texts" benchmark: sayings that circulate widely on social media as hadiths, a mix of authentic,
weak, fabricated and baseless ones. The list was compiled by the developer; every LABEL comes from الدرر السنية
(dorar.net, the challenge's approved hadith reference): the rulings of the entries whose wording matches the text.
Usage: python -m eval.make_circulated  →  eval/circulated.jsonl (review the printed table before using it)."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from rapidfuzz import fuzz

from app.dorar import DorarClient
from app.normalize import normalize_ar

HERE = Path(__file__).resolve().parent
TEXTS = [
    "اطلبوا العلم ولو في الصين", "النظافة من الإيمان", "حب الوطن من الإيمان", "اختلاف أمتي رحمة",
    "الجنة تحت أقدام الأمهات", "اعمل لدنياك كأنك تعيش أبدا واعمل لآخرتك كأنك تموت غدا", "من عرف نفسه فقد عرف ربه",
    "أدبني ربي فأحسن تأديبي", "نحن قوم لا نأكل حتى نجوع وإذا أكلنا لا نشبع", "صوموا تصحوا", "خير الأمور أوسطها",
    "الساكت عن الحق شيطان أخرس", "رجعنا من الجهاد الأصغر إلى الجهاد الأكبر", "اللهم بارك لنا في رجب وشعبان وبلغنا رمضان",
    "تفاءلوا بالخير تجدوه", "الدين المعاملة", "علموا أولادكم السباحة والرماية وركوب الخيل", "أنا مدينة العلم وعلي بابها",
    "أول ما خلق الله نور نبيك يا جابر", "لولاك ما خلقت الأفلاك", "اتقوا فراسة المؤمن فإنه ينظر بنور الله",
    "من لم تنهه صلاته عن الفحشاء والمنكر لم يزدد من الله إلا بعدا", "سيد القوم خادمهم", "من أصبح وهمه الدنيا فليس من الله في شيء",
    "العلم في الصغر كالنقش على الحجر", "ساعة لقلبك وساعة لربك",
    "إنما الأعمال بالنيات", "من تشبه بقوم فهو منهم", "لا تسبوا الدهر فإن الله هو الدهر", "الكلمة الطيبة صدقة",
    "تبسمك في وجه أخيك لك صدقة", "من غشنا فليس منا", "خيركم من تعلم القرآن وعلمه",
    "لا يؤمن أحدكم حتى يحب لأخيه ما يحب لنفسه", "المسلم من سلم المسلمون من لسانه ويده", "أحب الأعمال إلى الله أدومها وإن قل",
    "الحياء من الإيمان", "إن الله جميل يحب الجمال", "السفر قطعة من العذاب", "الدين النصيحة",
    "من حسن إسلام المرء تركه ما لا يعنيه", "الطهور شطر الإيمان", "يسروا ولا تعسروا وبشروا ولا تنفروا",
    "ليس الشديد بالصرعة إنما الشديد الذي يملك نفسه عند الغضب", "من صام رمضان إيمانا واحتسابا غفر له ما تقدم من ذنبه",
    "لا ضرر ولا ضرار", "ما ملأ آدمي وعاء شرا من بطن", "اللهم إنك عفو تحب العفو فاعف عني", "خير الناس أنفعهم للناس",
    "كلكم راع وكلكم مسؤول عن رعيته",
]
_WEAK = re.compile(r"ضعيف|موضوع|باطل|لا أصل|لا اصل|منكر|كذب|مكذوب|لم أجده|لا يصح|ليس بحديث|لا يثبت|واه")
_STRONG = re.compile(r"صحيح|حسن|أخرجه البخاري|أخرجه مسلم|إسناده صحيح|متفق")


def label(cards: list[dict], text: str) -> tuple[str, list[str]]:
    key = normalize_ar(text)
    close = [c for c in cards if c.get("text") and fuzz.partial_ratio(key, normalize_ar(c["text"])) >= 85]
    rulings = [f"{c['grade']} — {c['scholar']}، {c['book']}" for c in close[:6]]
    weak = sum(bool(_WEAK.search(c["grade"])) for c in close)
    strong = sum(bool(_STRONG.search(c["grade"])) and not _WEAK.search(c["grade"]) for c in close)
    if not close:
        return "no_entry", rulings
    if strong and not weak:
        return "authentic", rulings
    if weak and not strong:
        return "weak_or_fabricated", rulings
    return "mixed", rulings


def main() -> None:
    client = DorarClient()
    out = []
    for t in TEXTS:
        cards = client.search(t, words=10)
        lab, rulings = label(cards, t)
        out.append({"text": t, "label": lab, "dorar_rulings": rulings, "dorar_url": client.search_url(t, 10)})
        print(f"{lab:20} | {t[:45]:45} | {(rulings[0] if rulings else '')[:80]}", flush=True)
        time.sleep(1.0)
    (HERE / "circulated.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
