# Handoff: تحقّق (Tahaqqaq) — Hadith & Islamic text verification MVP

## Overview
Tahaqqaq lets preachers and Islamic content creators paste a text, image, or link and see whether it exists in approved hadith/Quran sources, how scholars graded it, and (for non-Arabic input) how accurate the translation is. The product principle is baked into the UI: **the tool relays scholars' gradings; it never issues its own verdict.** When no reliable match exists it explicitly abstains.

Scope: 4 screens + a component sheet. Arabic RTL is primary; the Result screen is also designed in English LTR. No login, no accounts.

## About the Design Files
The `.dc.html` files in this folder are **design references created in HTML** — prototypes showing the intended look and behavior, not production code. Recreate them in the target codebase (React/Next, Vue, etc.) using its own conventions. If there is no codebase yet, Next.js + Tailwind (with the tokens below as a theme) is a reasonable choice. All styling in the prototypes is inline, so every value can be read directly from the markup.

The files use a small custom runtime (`support.js`) — ignore it, it is only for the prototype renderer. Open `Tahaqqaq Canvas.dc.html` in a browser to see every screen side by side (desktop 1440 + mobile 390).

## Fidelity
**High-fidelity.** Colors, type, spacing, radii and copy are final. Recreate pixel-close. All hadith texts, numbers, percentages and gradings shown are **illustrative placeholders** and must be replaced by real data from the verification backend.

## Shared layout rules
- `dir="rtl"` on root when Arabic, `dir="ltr"` when English. Use CSS logical properties (`inset-inline-start`, `padding-inline-end`, `margin-inline`) so one implementation flips.
- Page: dark navy hero band (header + title) on `#0d1035` with a faint geometric pattern, then a light `#f5f4fb` body with white cards. Content max-width 1200px (860px on Home), horizontal padding `clamp(16px, 4vw, 64px)`.
- Geometric pattern: 72×72 tile, stroke `#c9c3ff` at 7% opacity: a 36px square, the same square rotated 45°, and a 6px-radius circle at the center. SVG data URI is in each file's hero `background-image`.
- Mobile (≤ 640px): nav links collapse behind a hamburger (44×44); multi-column flex rows wrap to single column; table on Recent becomes stacked cards.

## Screens

### 1. Home / Verify (`Home.dc.html`)
- **Hero**: h1 "تحقّق قبل أن تنشر" — Cairo 800, `clamp(38px, 4.4vw, 64px)`, line-height 1.25, white; the word "تنشر" in mint `#3ee6c0`. Sub-line Tajawal 400, 16–20px, line-height 1.8, lavender `#c9c3ff`, max-width 620px, centered. Hero padding-top `clamp(48px, 7vw, 96px)`, padding-bottom 150px; the input card overlaps it with `margin-top: -110px`.
- **Input card**: white, radius 24, shadow `0 2px 4px rgba(13,16,53,.06), 0 32px 64px -24px rgba(13,16,53,.35)`, overflow hidden.
  - Tab bar: 3 tabs (نص · صورة · رابط), each `flex:1; max-width:180px; height:58px`, Cairo 16, active = color `#4f3fd0`, weight 700, 3px bottom border `#7c6cf0`; inactive = `#5a5d80`, 500. Small meta chip after label ("أي لغة" / "OCR" / "URL"): Tajawal 11/500, bg `#f1effc`, color `#5a5d80`, radius 6, padding 2×7.
  - Text tab: textarea min-height 168, padding 18×20, border 1.5px `#e3e0f2`, radius 16, bg `#fbfaff`, Tajawal 19 / 1.8, `dir="auto"`. Focus: border `#7c6cf0`, bg white, ring `0 0 0 4px rgba(124,108,240,.15)`. Below: "اللغة: تُكتشف تلقائيًا" (mint 6px dot) and counter "N / ٢٠٠٠" (13px `#5a5d80`). Max 2000 chars.
  - Image tab: dropzone min-height 200, 2px dashed `#cfc9f5`, radius 18, bg `#faf9ff`; 52px icon tile `#ecebfe`; title Cairo 17/700 "اسحب صورة المنشور هنا"; helper 14px; secondary button "اختيار صورة" (44h). Accept PNG/JPG ≤ 10 MB; run OCR then verify.
  - URL tab: 60px field, `dir="ltr"`, monospace "https://" prefix in `#8e90ad`, placeholder `x.com/…/status/…`, helper text listing supported platforms.
  - Footer row (bg `#faf9fe`, top border `#ebe9f5`, padding 18×24): two helper lines (✓ green `#087a62` what it does; ✕ red `#a8324a` "ننقل أحكام المحدّثين من مصادرها، ولا نُصدر حكمًا آليًا") and the **primary button "تحقّق ←"** (56h, min-width 160, Cairo 18). Button disabled until input is non-empty.
- **Example chips**: label "جرّب مثالًا" (14/700 `#5a5d80`), 3 pill buttons (min-height 44, border `#e3e0f2`, radius 999, hover border `#7c6cf0`), each with a leading grade chip: صحيح (mint) "إنما الأعمال بالنيات"; موضوع (red) "حب الوطن من الإيمان"; "ترجمة غير دقيقة" (amber) "None of you is a Muslim until…". Clicking fills the textarea and switches to the text tab.
- **Footer**: logo, challenge name, links المصادر المعتمدة · المنهجية · روابط التحدي, disclaimer line 12px `#9d97d6`.

### 2. Result / Verification report (`Result.dc.html`) — core screen
Props/scenarios in the prototype: `partial`, `translation`, `uncertain`, `abstain`, `loading`; `lang: ar|en`.

- **Hero band** (navy): title "تقرير التحقق" Cairo 700 22–28px + time pill (13px, border `rgba(201,195,255,.25)`); right side note "ننقل أحكام المحدّثين من مصادرها، ولا نُصدر حكمًا آليًا." 14px lavender.
- **Status banner** (radius 20, padding 20–32, bg/border per state; flex-wrap, left block `flex:999 1 400px`, right block `flex:1 1 300px`):
  - 56×56 glyph tile (radius 16) in state color; small label "حالة النتيجة" 13/700 in state color; h2 state name Cairo 800 22–32px white; description 16px / 1.7 lavender.
  - States:
    | key | AR label | EN label | color | glyph | banner bg | banner border |
    |---|---|---|---|---|---|---|
    | verified | مؤيَّد بمصدر | Confirmed by source | `#3ee6c0` | ✓ (ink `#0d1035`) | `rgba(62,230,192,.08)` | `rgba(62,230,192,.45)` |
    | partial | مؤيَّد جزئيًا – اختلاف رواية | Partially confirmed – variant wording | `#7c6cf0` | ≈ (ink white) | `rgba(124,108,240,.14)` | `rgba(124,108,240,.6)` |
    | uncertain | غير مؤكد | Unconfirmed | `#f2a93b` | ؟ / ? (ink navy) | `rgba(242,169,59,.08)` | `rgba(242,169,59,.5)` |
    | abstain | لا مرجع – يُمتنع عن الحكم | No reference – verdict withheld | `#f07a8a` | — (ink navy) | `rgba(255,255,255,.04)` | `rgba(240,122,138,.55)` |
  - **Confidence box** (bg `rgba(13,16,53,.5)`, border `rgba(201,195,255,.12)`, radius 14, padding 18×20): label "مستوى الثقة" 14px; value Cairo 800 40px white (Arabic-Indic digits in AR, e.g. ٨٦٪); meter track 8px `rgba(255,255,255,.12)`, fill in state color, white tick at 75% ("حدّ القبول ٧٥٪" 12px `#9d97d6`); one-line reason 14px `#e4e1ff`.
  - Thresholds (also documented on Sources page): ≥90 verified · 75–89 partial · 50–74 uncertain · <50 abstain.
- **Body**: two columns, main `flex:999 1 560px`, aside `flex:1 1 320px`, gap 24. Cards: white, border `#ebe9f5`, radius 20, shadow `0 1px 2px rgba(13,16,53,.04), 0 12px 32px -16px rgba(13,16,53,.14)`, padding 18–28. Card titles Cairo 700 19px.
  - **مقارنة الصيغة (diff)** — shown for verified/partial/uncertain Arabic input. Legend: red swatch "مختلف في المُدخل", mint swatch "لفظ المصدر". Two panels (`flex:1 1 260px`): "النص المُدخل" on `#faf9fe`/border `#ebe9f5`; "الصيغة الصحيحة" on `#f3fdf9`/border `#c8f3e6`, label color `#087a62`. In the uncertain state the second label becomes "أقرب صيغة في المصادر". Text Tajawal 500 22px / 2.1, always `dir="rtl"`. Word-level diff tokens: deleted = bg `#fde4e8`, color `#a8324a`, 2px bottom border `#e7647a`; inserted = bg `#d6f8ee`, color `#076a55`, 2px bottom border `#3ee6c0`; both padding 0 4, radius 4.
  - **دقة الترجمة** — only when input is non-Arabic. Header flag chip "تحتاج تعديلًا" (amber bg `#fdf0d9`, ink `#8a5300`). Blocks: original Arabic (24px / 1.9, rtl); two panels "الترجمة المُدخلة" (bg `#fffafb`, border `#f6dde2`, label `#a8324a`) and "الترجمة المعتمدة" (mint panel), both `dir="ltr"` 18px / 1.8 with the same diff token styles; list "ملاحظات على المعنى": rows with severity chip (جوهرية red / تحسينية grey `#f1eff4`/`#5a5d80`) + 15px text, border `#ebe9f5`, radius 12.
  - **الحكم والمصدر** — header action "عرض في المصدر ↗" (40h small secondary button, opens source URL in new tab). In uncertain state an amber note row "الحكم أدناه للنص الأقرب، وليس للنص المُدخل." 6-cell grid (`repeat(auto-fit, minmax(200px,1fr))`, 1px `#ebe9f5` gutters, radius 14): النوع (chip `#f1effc`/`#4f3fd0`), الدرجة (grade chip Cairo 800 18px), المُحكِّم, المصدر, الكتاب والباب, الرقم (Cairo 800 22px). Cell label 13px `#5a5d80`, value 16/700.
    - Grade chips: صحيح `#dcfaf1`/`#087a62` · حسن `#ddf2f8`/`#0f6a85` · ضعيف `#fdf0d9`/`#8a5300` · موضوع `#fde4e8`/`#a8324a`. Types: حديث / أثر / آية / قول عالم / حكمة منتشرة.
    - Not rendered in the abstain state.
  - **ABSTAIN card** (replaces diff + grading): 48px circle with red border and "—"; h3 Cairo 800 20–24 "لا يوجد مرجع موثوق لهذا النص"; body copy explaining no verdict and no attribution; the input text in a dashed box (`1.5px dashed #d8d5e8`, bg `#f7f6fb`); "ما يمكنك فعله" bullet list (3 items, violet 6px dots); buttons: primary "طلب مراجعة بشرية", ghost "تحقق من نص آخر". The candidates list is still shown but every row is below threshold (grey bars) and no "المطابقة المعتمدة" tag appears. **Never show a grade or source attribution in this state.**
  - **Aside: أقرب النتائج المطابقة** — subtitle "حتى ٥ نتائج مرتبة حسب نسبة التطابق". Row: 26px rank circle (`#f1effc`/`#4f3fd0`), text 15px / 1.7 rtl, source line 13px, match % Cairo 800 15px, 4px bar. ≥75%: bar/percent violet `#7c6cf0`/`#4f3fd0`; <75%: grey `#c4c1d6`/`#5a5d80`. Top row ≥75% gets tag "المطابقة المعتمدة" (11/700 mint chip). Rows separated by 1px `#f0eef8`; footer note threshold.
  - **Aside: الإجراءات** — stacked full-width buttons 52h: primary "نسخ التقرير" (→ "✓ تم نسخ التقرير" for 2s), secondary "طلب مراجعة بشرية" (→ success row "أُرسل الطلب. يراجعه مختص خلال ٤٨ ساعة." bg `#dcfaf1`, ink `#087a62`), ghost "تحقق من نص آخر". In abstain state primary/secondary swap (review is primary).
- **Loading state**: banner replaced by a panel (bg `rgba(255,255,255,.04)`, border `rgba(201,195,255,.2)`): 44px spinner (3px ring `rgba(201,195,255,.2)`, top `#3ee6c0`, 0.9s linear) + "جارٍ التحقق…" Cairo 800 + sub-line. Step indicator, 4 equal columns: تطبيع → مطابقة → إسناد → تقرير. Each: 4px bar (done `#3ee6c0`, current `#7c6cf0`, todo `rgba(255,255,255,.12)`), 26px numbered circle (done: mint fill + ✓; current: violet border, white number; todo: lavender border), label Cairo 700 15, description 13px lavender. Body shows the input card plus a skeleton card (bars `#ebe9f5` / `#f1eff8`). Steps advance from the backend's progress events.
- **English variant**: identical layout mirrored LTR; all labels in `UI.en` inside `Result.dc.html`; digits Western; quoted Arabic text stays `dir="rtl"`.

### 3. Sources & methodology (`Sources.dc.html`) — static
- Hero: h1 "المصادر والمنهجية" Cairo 800 32–48, intro 16–19px lavender max 640.
- **المصادر المعتمدة**: 9 cards (`auto-fill, minmax(330px,1fr)`, gap 16): 56px logo placeholder (striped, replace with real logos), name Cairo 700 17, category chip (متون violet · أحكام mint · قرآن amber · ترجمات grey), usage sentence 14px / 1.7. List and copy are in the `SOURCES` array in the file.
- **المنهجية**: 4 numbered cards (36px navy tile with mint numeral) — تطبيع / مطابقة / إسناد / تقرير.
- **مستويات النتيجة**: 4 cards, each with the status badge + "متى يظهر" (threshold) + "ما نعرضه".
- **حدود الأداة**: navy block, radius 24, 5 bullets (8px mint rotated-square bullets), text 16px `#e4e1ff`.

### 4. Recent checks (`Recent.dc.html`)
- Hero: "سجل التحقق" + copy explaining session-only storage; ghost dark button "مسح السجل" (44h) when rows exist.
- Desktop table (grid `minmax(0,1fr) 250px 150px 110px 80px`, gap 16, row padding 16×24, header bg `#faf9fe` 13/700): النص (16/500 ellipsis, `dir` per text language + 12px input method "نص · إنجليزي / صورة / رابط") · النتيجة (status badge) · الحكم المنقول (14/700, colored by grade) · الوقت · "فتح ←" ghost 36h. Row hover bg `#fbfaff`.
- Mobile: each row is a tappable card (text, badge + grade row, meta line).
- Empty state: 64px icon tile, h2 Cairo 700 20 "لا توجد عمليات تحقق في هذه الجلسة", helper, primary "ابدأ التحقق".
- Storage: `sessionStorage` array of `{id, text, via, state, grade, time, resultId}`; cleared on tab close or "مسح السجل".

## Interactions & behavior
- Header: logo → Home; nav (تحقّق / المصادر والمنهجية / سجل التحقق), active item bg `rgba(124,108,240,.24)` white text; language toggle pill (ع / EN, 34h, active = white bg + navy text) switches `dir`, strings and numerals site-wide and persists in `localStorage`.
- Verify: on submit, navigate to Result in loading state; poll/stream progress to advance steps; render scenario by backend `state`.
- Copy report: writes plain-text report to clipboard (state, confidence, input, correct wording, grading, source, link).
- Request human review: POST request; show success row; disable the button afterwards.
- Hover: primary bg `#6a59e8`; secondary bg `#f4f2ff` + border `#7c6cf0`; ghost bg `#f4f2ff`; nav links white. No motion other than the spinner.
- Error states (see component sheet): source unreachable, OCR failed, URL unreachable, text > 2000 chars. Error card: border `#f6dde2`, 40px "!" tile `#fde4e8`/`#a8324a`, primary "إعادة المحاولة" + ghost "تعديل النص". Always state that no result was issued.

## State management
- `lang: 'ar' | 'en'` (persisted).
- Home: `tab`, `text`, `file`, `url`, `submitting`.
- Result: `status: 'loading' | 'done' | 'error'`, `step: 0..3`, `report` (`state`, `confidence`, `reason`, `input`, `correct`, `diff tokens`, `type`, `grade`, `grader`, `source`, `chapter`, `number`, `sourceUrl`, `translation?`, `candidates[]`), `copied`, `reviewRequested`.
- Recent: session list as above.

## Design tokens
Colors
- Navy bg `#0d1035` · Violet primary `#7c6cf0` · Violet hover `#6a59e8` · Violet ink (text/links on light) `#4f3fd0` · Violet tint `#f1effc` / `#ecebfe`
- Mint `#3ee6c0` · Mint ink `#087a62` · Mint tint `#dcfaf1` · diff-ins `#d6f8ee` / `#076a55`
- Lavender secondary text `#c9c3ff` · dim lavender `#9d97d6` · light text on dark `#e4e1ff`
- Amber `#f2a93b` · Amber ink `#8a5300` · Amber tint `#fdf0d9`
- Red `#e7647a` (banner `#f07a8a`) · Red ink `#a8324a` · Red tint `#fde4e8` · neutral-red tint `#f1eff4`
- Teal (حسن) `#0f6a85` / `#ddf2f8`
- Ink `#14173d` · body `#3d4066` · muted `#5a5d80` · placeholder `#8e90ad`
- Border `#ebe9f5` · field border `#e3e0f2` · secondary button border `#d9d5f5` · divider `#f0eef8` · surface `#f5f4fb` · card `#ffffff` · panel `#faf9fe`
- Links: `a { color:#4f3fd0 } a:hover { color:#7c6cf0 }`

Typography (Google Fonts: Cairo 500–800, Tajawal 400/500/700)
- Display h1: Cairo 800, clamp(38,4.4vw,64), lh 1.25
- Page h1: Cairo 800, clamp(30–32, 3.2–3.6vw, 44–48), lh 1.3
- Banner h2 / section h2: Cairo 800, clamp(22–24, 2.4–2.6vw, 30–32)
- Card title: Cairo 700 19 · sub-title: Cairo 700 16–18 · button: Cairo 700 16 (M 15, S 14)
- Quoted text: Tajawal 500 22, lh 2.0–2.1 · original Arabic in translation card 24 / 1.9 · translation 18 / 1.8
- Body: Tajawal 400 16 / 1.7 · small 15 / 1.7 · 14 / 1.6 · label 13 / 500 · caption 12 (minimum)
- Confidence value: Cairo 800 40 · hadith number: Cairo 800 22 · grade chip: Cairo 800 18
- Mono annotations (handoff only): ui-monospace

Spacing scale: 4 · 8 · 12 · 16 · 20 · 24 · 32 · 40 · 56 · 72. Card padding `clamp(18px, 2.2vw, 28px)`.
Radii: 6 (meta chip) · 8 (grade chip) · 10 (S button) · 12 (M button, list row) · 14 (L button, panel) · 16 (field, glyph tile) · 18 (dropzone) · 20 (card) · 24 (input card, navy block) · 999 (pills).
Shadows: card `0 1px 2px rgba(13,16,53,.04), 0 12px 32px -16px rgba(13,16,53,.14)`; raised `0 2px 4px rgba(13,16,53,.06), 0 32px 64px -24px rgba(13,16,53,.35)`; primary button `0 8px 20px -8px rgba(124,108,240,.7)`; focus ring `0 0 0 4px rgba(124,108,240,.15)`.
Sizes: header 72h · buttons L 52 / M 44 / S 40 (min tap 44 on mobile) · tabs 58h · field 56–60h · badge 6×14 pill 14/700 · meter 8h · candidate bar 4h.

## Assets
- Logo mark: 22px violet square rotated 45° with an 8px mint circle (CSS only). Replace with the official challenge/brand mark if available.
- Source logos: striped placeholders — supply real logos.
- Geometric pattern: inline SVG data URI (in each hero `background-image`).
- Icons: text glyphs (✓ ≈ ؟ — ↗ ← ↑ !) — swap for an icon set (e.g. Lucide) keeping the same sizes.

## Files
- `Tahaqqaq Canvas.dc.html` — all screens, desktop + mobile, every Result state, EN variant, component sheet (open this first).
- `Home.dc.html`, `Result.dc.html`, `Sources.dc.html`, `Recent.dc.html` — standalone screens. `Result.dc.html` contains all AR/EN strings (`UI`), state definitions (`ST`), grade chips (`GR`) and sample scenarios (`SC`) in its script.
- `Header.dc.html`, `Footer.dc.html` — shared chrome.
- `Components.dc.html` — mini design system sheet.
- `support.js` — prototype runtime only; do not port.
