"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { health } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { num } from "@/lib/format";
import { STATE } from "@/lib/tokens";

type Cat = "matn" | "rulings" | "quran" | "tafsir" | "translations" | "glossary";
const CAT: Record<Cat, { bg: string; fg: string }> = {
  matn: { bg: "#ecebfe", fg: "#4f3fd0" }, rulings: { bg: "#dcfaf1", fg: "#087a62" }, quran: { bg: "#fdf0d9", fg: "#8a5300" },
  tafsir: { bg: "#fdf0d9", fg: "#8a5300" }, translations: { bg: "#f1eff4", fg: "#3d4066" }, glossary: { bg: "#ddf2f8", fg: "#0f6a85" },
};

const SOURCES: { ar: string; en: string; cat: Cat; useAr: string; useEn: string; url: string }[] = [
  { ar: "الموسوعة الحديثية — الدرر السنية", en: "Dorar.net Hadith Encyclopedia", cat: "rulings", useAr: "المرجعية المعتمدة للحديث في التحدي: لكل حديث مطابق تُجلب منها أحكام المحدّثين (المحدث، المصدر، الرقم، خلاصة الحكم) وشرح الحديث، وتُعرض بنصّها مع الرابط، وتُحفظ في قاعدة البيانات.", useEn: "The challenge's approved hadith reference: for every matched hadith the scholars' rulings (scholar, source, number, ruling) and the hadith's explanation are fetched from it, shown verbatim with the link, and cached in the database.", url: "https://dorar.net/hadith" },
  { ar: "صحيح البخاري وصحيح مسلم", en: "Sahih al-Bukhari & Sahih Muslim", cat: "matn", useAr: "الأحاديث الصحيحة من الصحيحين: مطابقة المتن، والكتاب والرقم (ترقيم محمد فؤاد عبد الباقي لمسلم)، والحكم بإخراج المصنّف له.", useEn: "The authentic hadiths of the two Sahihs: text matching, book and number (Abd al-Baqi numbering for Muslim), ruling by the compiler's inclusion.", url: "https://dorar.net/hadith" },
  { ar: "السنن الأربعة", en: "The four Sunan", cat: "matn", useAr: "أبو داود والترمذي والنسائي وابن ماجه: لا يُنسب منها حديث إلا بحكم محقق منقول (الألباني، شعيب الأرناؤوط وغيرهم)؛ وما لا حكم له يُعرض «نصًا قريبًا» فقط.", useEn: "Abu Dawud, al-Tirmidhi, al-Nasa'i, Ibn Majah: a hadith is attributed only with a recorded editor's ruling (al-Albani, Shuaib al-Arna'ut…); without one it is shown as a closest text only.", url: "https://dorar.net/hadith" },
  { ar: "البيانات المفتوحة للكتب الستة (للمطابقة)", en: "Open Six Books dataset (for matching)", cat: "matn", useAr: "مصدر نصوص البحث: مجموعة hadith-api المفتوحة (ترخيص CC0، مأخوذة من sunnah.com) بالمتون والترجمة الإنجليزية المنشورة وأحكام المحققين المطبوعة معها. تُستخدم للفهرسة والمطابقة، ويُعرض بجانبها حكم الدرر السنية للتثبّت.", useEn: "Where the searchable texts come from: the open hadith-api dataset (CC0, derived from sunnah.com) with the texts, the published English translation and the editors' grades. Used for indexing and matching; the Dorar.net rulings are shown next to it for confirmation.", url: "https://github.com/fawazahmed0/hadith-api" },
  { ar: "السلسلة الضعيفة والموضوعات", en: "Al-Silsilah al-Da'ifah & al-Mawdu'at", cat: "rulings", useAr: "قائمة مُراجَعة يدويًا للأحاديث المنتشرة خارج الكتب الستة بأحكام الألباني وابن الجوزي والصغاني وغيرهم كما في الدرر السنية.", useEn: "A hand-reviewed list of circulated sayings outside the Six Books with the rulings of al-Albani, Ibn al-Jawzi, al-Saghani and others as recorded on Dorar.net.", url: "https://dorar.net/hadith" },
  { ar: "مصحف المدينة — مجمع الملك فهد", en: "Madinah Mushaf — King Fahd Complex", cat: "quran", useAr: "دوره كشف الآية المنسوبة إلى النبي ﷺ على أنها حديث، وتصحيح الآية المحرّفة: النص بالرسم العثماني، والسورة والآية، ورابط الآية في الموسوعة القرآنية quranpedia.net.", useEn: "Used to detect a verse quoted as a saying of the Prophet ﷺ and to correct misquoted verses: Uthmani text, surah and ayah, and a link to the verse on quranpedia.net.", url: "https://quranpedia.net" },
  { ar: "موسوعة التفسير — الدرر السنية", en: "Dorar.net Tafsir Encyclopedia", cat: "tafsir", useAr: "الشرح الموسّع للآية ملخّص آليًا من نص التفسير فيها فقط، مع الرابط.", useEn: "The extended explanation of a verse is summarised from its tafsir text there only, with the link.", url: "https://dorar.net/tafseer" },
  { ar: "الترجمات المعتمدة", en: "Approved translations", cat: "translations", useAr: "ترجمة الهلالي وخان لمعاني القرآن (طبعة مجمع الملك فهد)، والترجمة الإنجليزية المنشورة للكتب الستة، للمقارنة مع ترجمة المستخدم.", useEn: "The Hilali & Khan translation of the Qur'an's meanings (King Fahd Complex edition) and the published English translations of the Six Books, compared against the user's translation.", url: "https://quranenc.com/en/browse/english_hilali_khan" },
  { ar: "الجمهرة — موسوعة مفردات المحتوى الإسلامي", en: "Al-Jamhara — Islamic content glossary", cat: "glossary", useAr: "تعريفات المصطلحات الشرعية (التقوى، الزكاة، الصدقة، السنة، الجهاد…) منقولة منها مع رابط المدخل؛ تُنقل بلفظها ويُشرح معناها ولا تُترجم حرفيًا.", useEn: "Definitions of terms of art (taqwa, zakat, sadaqah, sunnah, jihad…) quoted from it with the entry link; kept as terms and explained, never translated literally.", url: "https://islamic-content.com" },
];

const STEPS = [
  { ar: ["تطبيع", "تطبيع موحّد لكل مُدخل (نص، صورة بعد القراءة الآلية، رابط): إزالة التشكيل وعلامات الاقتباس والألقاب الشريفة وصيغ النسبة، وتوحيد الهمزات والتاء المربوطة. وللصور والروابط والنصوص الطويلة يستخلص نموذج لغوي المقاطع المقتبسة بعد التحقق من أنها موجودة في المُدخل حرفيًا."], en: ["Normalize", "One normaliser for every input (text, OCR'd image, link): diacritics, quotes, honorifics and attribution phrases removed, letter forms unified. For images, links and long texts a language model extracts the quoted segments, each validated as literally present in the input."] },
  { ar: ["مطابقة", "تدرّج صريح: تطابق حرفي أو احتواء ← تشابه ثلاثي الحروف مع تغطية الكلمات ← تشابه دلالي (تضمينات متعددة اللغات في pgvector) مشروط بوجود تطابق لفظي ← وإلا امتناع مع عرض أقرب النتائج. المطابقة الحرفية تحكم؛ الدلالة تُرتّب فقط."], en: ["Match", "An explicit cascade: exact/substring → trigram similarity with word coverage → semantic similarity (multilingual embeddings in pgvector) conditioned on some shared wording → otherwise abstain with the nearest results. Wording decides; meaning only ranks."] },
  { ar: ["إسناد", "الحكم يُقرأ بنصّه من سجل المصدر، وتُجلب بجانبه أحكام المحدّثين من الموسوعة الحديثية في الدرر السنية للحديث المطابق. لا يُنسب حديث بلا حكم منقول، ولا يُنتج أي نموذج حكمًا."], en: ["Attribute", "The ruling is read verbatim from the source record, and the scholars' rulings from the Dorar.net Hadith Encyclopedia are fetched next to it for the matched hadith. No hadith is attributed without a recorded ruling, and no model ever produces a grade."] },
  { ar: ["تقرير", "النتيجة ومستوى الثقة والفروق، أو الامتناع. الشرح المولَّد آليًا (موجز أو موسّع، بأي لغة) معنون ومفصول عن النص المنقول، ويُراجع نص الشرح لغويًا قبل عرضه، ولا يُعرض إلا بعد ثبوت النتيجة من المصدر."], en: ["Report", "The result, confidence and differences, or an abstention. AI wording (brief or extended, in any language) is labelled and kept apart from quoted text, is checked to be in the requested language, and is only shown after the source has settled the result."] },
];

const LEVELS: { key: keyof typeof STATE; whenAr: string; whenEn: string; showAr: string; showEn: string }[] = [
  { key: "verified", whenAr: "تطابق النص مع مصدر معتمد بنسبة ٩٠٪ فأكثر.", whenEn: "The text matches an approved source at 90% or more.", showAr: "الحكم المنقول، والمصدر، ورابط الموضع.", showEn: "The relayed grade, the source and a link to it." },
  { key: "partial", whenAr: "تطابق بين ٧٥٪ و٨٩٪، أو اختلاف ألفاظ بين الروايات.", whenEn: "A match between 75% and 89%, or variant wording between narrations.", showAr: "الفروق مظلّلة، والصيغة الصحيحة، والحكم.", showEn: "Highlighted differences, the correct wording and the grade." },
  { key: "unreliable", whenAr: "أعلى تطابق ٧٥٪ فأكثر مع نص حكمه المنقول موضوع أو ضعيف أو لا أصل له.", whenEn: "Best match 75% or more with a text whose recorded ruling is fabricated, weak or baseless.", showAr: "الحكم بنصّه ومصدره، واللفظ كما ورد في مصدر الحكم، وتنبيه بعدم النشر منسوبًا.", showEn: "The verbatim ruling and its source, the wording as recorded, and a warning not to attribute it." },
  { key: "uncertain", whenAr: "أعلى تطابق بين ٥٠٪ و٧٤٪، أو نص قريب في المعنى بلفظ آخر، أو نص بلا حكم منقول.", whenEn: "Best match between 50% and 74%, a text close in meaning, or a text with no recorded ruling.", showAr: "أقرب نص وحكمه، مع تنبيه أنه ليس النص المُدخل.", showEn: "The closest text and its grade, flagged as not being your text." },
  { key: "abstain", whenAr: "أعلى تطابق أقل من ٥٠٪، أو طلب لإنشاء حديث.", whenEn: "Best match below 50%, or a request to invent a hadith.", showAr: "لا حكم إطلاقًا. أقرب النتائج للمقارنة، وزر طلب المراجعة.", showEn: "No verdict at all. Closest results for comparison and a review request button." },
  { key: "referral", whenAr: "سؤال شخصي عن حكم شرعي (هل يجوز لي…).", whenEn: "A personal question about a ruling (is it permissible for me…).", showAr: "إحالة إلى أهل العلم؛ لا بحث ولا حكم.", showEn: "Referral to scholars; no search and no verdict." },
];

const LIMITS = {
  ar: [
    "لا تُصدر الأداة حكمًا من عندها؛ كل حكم منقول بنسبته إلى قائله من سجل المصدر.",
    "لا تُغني عن سؤال أهل العلم، خاصة في الفتوى والأحكام.",
    "التغطية محصورة في المصادر أعلاه؛ غياب النص عنها لا يعني أنه مكذوب.",
    "قائمة الأحاديث المنتشرة بأحكامها صغيرة ومُراجَعة يدويًا، وتحتاج مراجعة مختص قبل الاعتماد.",
    "استخراج النص من الصور قد يخطئ في الخطوط المزخرفة؛ راجع النص المستخرج قبل التحقق.",
    "الترجمة الآلية والشرح المولَّد يُستخدمان للعرض فقط، ولا يُعرضان بوصفهما حكمًا أو ترجمة معتمدة.",
    "أحكام الدرر السنية تُجلب بالبحث بنص الحديث المطابق وقد تظهر معها روايات قريبة؛ نرتّب أولًا ما يطابق الكتاب والرقم، والرابط يفتح البحث نفسه للتثبّت.",
    "الشرح الموسّع لا يُولَّد إلا من نص شرح الحديث أو التفسير في الدرر السنية؛ وإن لم يوجد شرح لا يُعرض شيء.",
    "الشرح المولَّد اختياري: عند تفعيله يُرسَل النص إلى مزوّد النموذج اللغوي (Gemini أو Groq أو غيرهما) لصياغة الشرح فقط، ولا يُنتج النموذج أي حكم.",
  ],
  en: [
    "The tool issues no verdict of its own; every ruling is attributed to its author from the source record.",
    "It is no substitute for asking scholars, especially for fatwas and rulings.",
    "Coverage is limited to the sources above; absence from them does not make a text fabricated.",
    "The curated list of circulated sayings is small and hand-reviewed; a specialist should review it before relying on it.",
    "OCR may misread decorative fonts; review the extracted text before verifying.",
    "Machine translation and generated explanations are for display only and are never shown as an approved ruling or translation.",
    "Dorar.net rulings are fetched by searching the matched hadith's text and related narrations may appear; entries with the same book and number come first, and the link opens the same search for confirmation.",
    "The extended explanation is only generated from Dorar.net's hadith explanation or tafsir text; when there is none, nothing is shown.",
    "The generated explanation is optional: when enabled, the text is sent to the language-model provider (Gemini, Groq or another) for wording only; the model never produces a ruling.",
  ],
};

export default function SourcesPage() {
  const t = useTranslations("sources");
  const { lang } = useLang();
  const [counts, setCounts] = useState<Record<string, number> | null>(null);
  useEffect(() => { health().then((h) => setCounts(h?.counts ?? null)); }, []);
  const L = (ar: string, en: string) => (lang === "ar" ? ar : en);
  const h2 = { margin: 0, fontWeight: 800, fontSize: "clamp(24px,2.4vw,30px)" } as const;
  return (
    <>
      <section className="hero">
        <div className="wrap" style={{ padding: "clamp(40px,5vw,72px) var(--gutter)", display: "flex", flexDirection: "column", gap: 14 }}>
          <h1 className="font-cairo" style={{ margin: 0, fontWeight: 800, fontSize: "clamp(32px,3.6vw,48px)", lineHeight: 1.3, color: "#fff" }}>{t("title")}</h1>
          <p style={{ margin: 0, maxWidth: 640, fontSize: "clamp(16px,1.4vw,19px)", lineHeight: 1.8, color: "#c9c3ff", textWrap: "pretty" }}>{t("intro")}</p>
        </div>
      </section>
      <main id="main" className="wrap" style={{ padding: "48px var(--gutter) 72px", display: "flex", flexDirection: "column", gap: 56, width: "100%" }}>
        <section style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", justifyContent: "space-between", gap: "8px 16px" }}>
            <h2 className="font-cairo" style={h2}>{t("approved")}</h2>
            <span style={{ fontSize: 14, color: "#5a5d80" }}>{num(SOURCES.length, lang)} · {t("approvedSub")}</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(100%,330px),1fr))", gap: 16 }}>
            {SOURCES.map((s) => (
              <article key={s.en} className="card" style={{ padding: 20, display: "flex", gap: 16, alignItems: "flex-start" }}>
                <a href={s.url} target="_blank" rel="noreferrer" style={{ flex: "none", width: 56, height: 56, borderRadius: 14, border: "1px solid #e3e0f2", background: "repeating-linear-gradient(135deg,#f5f4fb 0 6px,#ebe9f5 6px 7px)", display: "grid", placeItems: "center", fontFamily: "ui-monospace, Menlo, monospace", fontSize: 10, color: "#8e90ad" }}>↗</a>
                <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 8 }}>
                  <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
                    <h3 className="font-cairo" style={{ margin: 0, fontWeight: 700, fontSize: 17, lineHeight: 1.4 }}><a href={s.url} target="_blank" rel="noreferrer" style={{ color: "inherit" }}>{L(s.ar, s.en)}</a></h3>
                    <span style={{ padding: "2px 10px", borderRadius: 999, fontSize: 12, fontWeight: 700, background: CAT[s.cat].bg, color: CAT[s.cat].fg }}>{t(`cat.${s.cat}`)}</span>
                  </div>
                  <p style={{ margin: 0, fontSize: 14, lineHeight: 1.7, color: "#3d4066", textWrap: "pretty" }}>{L(s.useAr, s.useEn)}</p>
                </div>
              </article>
            ))}
          </div>
          {counts && (
            <p style={{ margin: 0, fontSize: 14, color: "#5a5d80" }}>
              {t("data")}: {num(counts.hadith ?? 0, lang)} {t("hadith")} · {num(counts.quran ?? 0, lang)} {t("quran")} · {num(counts.seed ?? 0, lang)} {t("seed")} · {num(counts.glossary ?? 0, lang)} {t("glossaryCount")}
            </p>
          )}
        </section>

        <section id="method" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <h2 className="font-cairo" style={h2}>{t("method")}</h2>
          <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%,230px),1fr))", gap: 16 }}>
            {STEPS.map((s, i) => (
              <li key={i} className="card" style={{ boxShadow: "none", padding: 22, display: "flex", flexDirection: "column", gap: 10 }}>
                <span className="font-cairo" style={{ width: 36, height: 36, borderRadius: 10, background: "#0d1035", color: "#3ee6c0", display: "grid", placeItems: "center", fontWeight: 800, fontSize: 16 }}>{num(i + 1, lang)}</span>
                <h3 className="font-cairo" style={{ margin: 0, fontWeight: 700, fontSize: 18 }}>{L(s.ar[0], s.en[0])}</h3>
                <p style={{ margin: 0, fontSize: 14, lineHeight: 1.7, color: "#3d4066" }}>{L(s.ar[1], s.en[1])}</p>
              </li>
            ))}
          </ol>
        </section>

        <section style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <h2 className="font-cairo" style={h2}>{t("levels")}</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%,260px),1fr))", gap: 16 }}>
            {LEVELS.map((l) => (
              <LevelCard key={l.key} k={l.key} when={L(l.whenAr, l.whenEn)} show={L(l.showAr, l.showEn)} />
            ))}
          </div>
        </section>

        <section style={{ background: "#0d1035", borderRadius: 24, padding: "clamp(24px,3vw,40px)", display: "flex", flexDirection: "column", gap: 18 }}>
          <h2 className="font-cairo" style={{ ...h2, color: "#fff" }}>{t("limits")}</h2>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%,420px),1fr))", gap: "12px 32px" }}>
            {LIMITS[lang].map((x) => (
              <li key={x} style={{ display: "flex", gap: 12, fontSize: 16, lineHeight: 1.7, color: "#e4e1ff" }}>
                <span style={{ flex: "none", width: 8, height: 8, marginTop: 10, background: "#3ee6c0", transform: "rotate(45deg)" }} />{x}
              </li>
            ))}
          </ul>
        </section>
      </main>
    </>
  );
}

function LevelCard({ k, when, show }: { k: keyof typeof STATE; when: string; show: string }) {
  const t = useTranslations("sources");
  const s = useTranslations("states");
  const st = STATE[k];
  return (
    <article className="card" style={{ boxShadow: "none", padding: 22, display: "flex", flexDirection: "column", gap: 14 }}>
      <span className="chip" style={{ alignSelf: "flex-start", padding: "6px 14px", fontSize: 14, background: st.chipBg, color: st.chipFg }}><span className="dot" style={{ width: 8, height: 8, background: st.dot }} />{s(`${k}.label`, { grade: "موضوع / ضعيف" })}</span>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 12, fontWeight: 700, color: "#5a5d80" }}>{t("when")}</span><p style={{ margin: 0, fontSize: 15, lineHeight: 1.7 }}>{when}</p></div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 12, fontWeight: 700, color: "#5a5d80" }}>{t("show")}</span><p style={{ margin: 0, fontSize: 15, lineHeight: 1.7 }}>{show}</p></div>
    </article>
  );
}
