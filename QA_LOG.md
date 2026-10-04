# QA log — Tahaqqaq end-to-end hardening

Format: `scenario — what was wrong — what changed`. Decisions taken without asking are marked **Decision**.

- **Decision**: e2e runs with Playwright (`frontend/e2e`) against the docker-compose stack using the installed Google Chrome (`channel: chrome`) to avoid a browser download. Fixture pages and test images are served by a `fixtures` nginx service (`docker compose --profile qa up -d fixtures`), reachable from the API container as `http://fixtures/…` and from the host on `:8089`.
- **Decision**: test images are rendered with headless Chrome using Google Fonts Tajawal/Cairo (`qa/fixtures/images/*.html`) instead of PIL, because PIL cannot shape Arabic (no joining/ligatures) without libraqm; a blurry variant is derived with PIL.
- **Decision**: API-level checks live in `backend/tests/integration/test_stack.py` (run with `TAHQAQ_STACK=1`), skipped in the unit suite.
- Link input: non-http schemes (`javascript:`, `ftp:`, `mailto:`) — crashed with a 500 (`httpx.InvalidURL` is not an `HTTPError`) — rejected explicitly with a 422 and the catch widened; non-HTML content types are rejected too.
- Image input: English text image — the Arabic-only OCR pass "won" because junk Arabic letters outnumbered the Latin ones — pass selection now counts real single-script words instead of Arabic letters.
- Text: sahih with typos + extra words — scored "uncertain" (72) because one-letter typos in short words (بالنيه/بالنيات, امرء/امري) failed the 80-point fuzzy word match — threshold is 70 for words of 6 letters or fewer.
- Text: English paraphrase of a sahih hadith — scored "uncertain" because the English matching key still contained the narrator preamble ("Narrated 'Umar… said:") and wording weighed 75% — English input is always a translation, so meaning now weighs 50% for English, and the English key/embeddings are built from the Prophet's words only (`ingest/reembed_en.py` re-indexes English in ~15 min).
- Recent checks: opening a row showed nothing — the history row used the backend report id while the cached report was keyed by the session id in the URL — the session id is now the single key.
- e2e harness: Uthmani script writes زِدْنِى with ى; assertion made script-tolerant. Language seeding happens once per tab so toggle persistence can be tested.
- Text: English paraphrase still "uncertain" (70) after the re-index — MiniLM paraphrase cosines for translation variants of the same hadith sit at 0.8–0.9 while unrelated English sits near 0.25, so the English semantic scale is now (cos−0.25)/0.65 (Arabic unchanged). Checked: paraphrase → partial 77, unrelated English sentence → abstain 32, gibberish → abstain 45, "Whoever believes in Allah and the Last Day…" → verified Bukhari 6136.

## Runs

| Run | Result |
|---|---|
| e2e run 1 | 43 passed, 1 skipped (LLM block: no `ANTHROPIC_API_KEY` on the stack) |
| e2e run 2 (extended: uncertain state, loading/banner/recent × ar/en) | 48 passed, 1 skipped |
| e2e run 3 | 48 passed, 1 skipped |
| backend unit (`pytest`) | 12 passed |
| API integration (`TAHQAQ_STACK=1 pytest tests/integration`) | 26 passed |
| 5xx in API logs across all runs | 0 |
| browser `pageerror` / console errors (network-status lines for intentionally invalid uploads/links excluded) | 0 |

- **Decision**: console-error assertion ignores Chrome's "Failed to load resource: 415/422/413" lines, which the browser prints for the intentionally invalid image and link requests; uncaught page errors and all other console errors fail the test.
- **Decision**: the LLM explanation scenario is skipped when `/health` reports `llm: false`; it cannot be exercised without a key.
- Screenshots: `qa/screenshots/{ar,en}-*.png` — one per state (verified, partial, uncertain, unreliable-mawdu, unreliable-daif, translation, translation-issues, quran, quran-misquote, abstain, referral), per input path (image, image-rejected, link, link-error) and cross-cutting (loading, banner, recent, recent-empty, sources), both languages.
- Image (smoke screenshot review): an OCR'd post scored 77% instead of ~100% and the attribution words showed as deletions — OCR had dropped «الله» from «صلى الله عليه وسلم» so the attribution prefix was not stripped, and short inputs never went through quote extraction — the attribution regex now tolerates OCR variants and a trailing «رواه …», and any input that wraps a quoted/attributed span is verified on that span (attribution is detected on the full text so the Qur'an-as-hadith note still fires).
- Arabic UI (smoke screenshot review): "الكتاب والباب" showed an English section title ("Belief") because the open dataset only carries English section names — Arabic output now shows "الكتاب رقم N" and the English title stays in the English UI.

## LLM provider layer

- **Decision**: the explanation/transcription step runs behind one OpenAI-compatible client (`backend/app/llm.py`) with a provider chain `LLM_PROVIDER` + `LLM_FALLBACKS`; a provider that answers 429/5xx or times out is skipped and cooled down for 45 s; when every provider fails the card is absent and the verdict is untouched. Default models: gemini `gemini-flash-latest`, groq `openai/gpt-oss-120b` (Groq no longer serves `llama-3.3-70b-versatile`), openrouter `qwen/qwen3.8-27b:free` (vision-capable). Cerebras left unconfigured as requested.
- **Decision**: the e2e matrix sends `explain:false` (via `localStorage tahqaq.explain=0`) so ~60 verifications per run do not burn free-tier quotas; the dedicated LLM test enables it and asserts the labelled, separated card.
- **Decision**: because the free tiers may use submitted text, the banner and the Sources page now say that the text is sent to the provider for wording only when the explanation is enabled.

## Matching cascade (spec round)

- **Decision**: `normalize_ar` (`backend/app/normalize.py`) is the single matching normaliser: quotes, emoji/symbols, tashkeel/tatweel, honorifics anywhere (ﷺ، صلى الله عليه وسلم، رضي الله عنه/عنها/عنهم، عليه السلام، رحمه الله…), lead-ins at the start (قال رسول الله:, عن فلان قال:, حدثنا…, روى…) and trailing «رواه …». It is applied to every query (`matcher.normalize_query`) and to every stored key (`ingest/renormalize.py` re-keyed 5,690 records and re-embedded their Arabic windows). The UI never shows normalised strings: the comparison panel shows the user's original words against the record's original vocalised text.
- **Decision**: the cascade is exact/substring → trigram (`word_similarity ≥ 0.6` with content-word coverage, or strong blended wording ≥ 80 for typos/extra words) → vector (cosine ≥ 0.80 **and** some shared wording ≥ 45) → abstain with nearest results. Reason for the extra wording condition: MiniLM scores formulaic but unrelated Arabic («من قرأ هذا النص غُفر له كل ذنب» vs «من نفّس عن مؤمن كربة…») at cosine 0.86, so meaning alone would turn invented texts into "closest text" instead of abstaining. The displayed confidence is the blended score clamped into the admitting stage's band, so the Sources-page thresholds and the cascade agree.
- **Decision**: English input keeps the meaning-weighted scoring (translations legitimately vary); its stage 2 is lexical ≥ 70 or blended ≥ 75.
- OCR: OpenCV preprocessing (grayscale, 2× upscale, deskew up to 15°, adaptive threshold) runs Tesseract on the binarised and the plain variant and keeps the pass with more real words, because adaptive thresholding helps photos but can hurt clean screenshots.
- Links: main content via trafilatura → readability-lxml → densest leaf blocks; the whole main text (≤ 3000 chars) goes to the pipeline, which verifies every quoted/attributed segment and every sentence longer than 6 words, keeps the best and lists the other segments' matches under nearest results. Failures (blocked, login, no text, non-http, redirect loop) return 422 with «تعذّر قراءة الرابط — الصق النص مباشرة».
- LLM: a provider that times out no longer stalls the report; the chain has a 20 s total budget. Gemini default switched to `gemini-flash-lite-latest` (flash-latest regularly exceeded 15 s).
- New: `/api/explain` + a language dropdown on the explanation card (25 languages) re-words the same facts without re-verifying; the choice is remembered in `localStorage`.

## AI middle step for images, links and long pastes

- **Decision**: when a provider is configured, OCR text, page text and long pastes go through `llm.extract_segments`: certain-only OCR fixes and the list of quoted segments (hadith / verse / saying) without attribution phrases. Every segment is validated by fuzzy containment in the input (ungrounded segments are dropped) and a "cleaned" text that drifts from the input is discarded, so the model cannot inject text. Segments are merged with the rule-based candidates, each is verified separately, the best becomes the report and all of them are listed in a new "المقاطع المستخلصة" card with their own match, confidence and a one-click re-verify. The extractor's `type` is a guess, never a ruling. Without a provider the rule-based path runs unchanged.
- Images: when a vision provider is configured, the transcription itself comes from the model (Tesseract + OpenCV is the fallback).
- Explanation language: the target language is now a hard requirement in the system prompt and the answer's script is checked; a wrong-language answer is retried once and otherwise rejected (verified in tr, id, ur, fr, ru, zh, hi, sw, de, es, ms, fa).
- Extended explanation mode (brief / شرح موسّع): meaning, vocabulary and lessons of the matched source text only, no attributions to commentary books, labelled with its own warning; unavailable for abstain/referral/uncertain. For verses it points to dorar.net/tafseer.
- OpenRouter default moved to `google/gemma-4-26b-a4b-it:free`: the free Qwen spends its whole token budget on hidden reasoning and returns empty content.

## Judging-criteria pass

- Benchmark: `backend/eval/make_benchmark.py` builds 98 labelled inputs from the ingested data (fixed seed); `run_benchmark.py` reports accuracy and wrong-attribution rate to `qa/benchmark.md`. First run showed 3 invented texts landing on "closest text" through the semantic stage (MiniLM cosine 0.91–0.99 to formulaic hadiths) — the semantic stage now also needs a trigram hit from the index (≥ 0.55); result 97% accuracy, 6/6 invented abstain, 3 misses that all point at the same hadith under another number (accepted as equivalents only when the wording is identical).
- Accessibility: skip link, visible focus ring, live regions on the loading panel and status banner, labelled language toggle / fields / confidence meter, decorative glyphs hidden from screen readers.
- Methodology page now describes the actual pipeline (normaliser, AI extraction with grounding, cascade, verbatim ruling, labelled explanation).
- `README.ar.md` and `qa/judging-self-assessment.md` added for the judges.

## OCR: sunnah.com screenshot (user report)

- Image: a sunnah.com screenshot of Bukhari 1 showed only one line in the review box — the vision model had transcribed all five lines correctly, but `/api/ocr` returned `pick_quote(full)`, which split on the image's visual line breaks and kept the single line containing «صلى الله عليه وسلم», cutting the hadith in half — the endpoint now returns the whole transcription, reflowed into flowing text, and the review box is sized to it.
- Full hadith with its chain of narrators (typed, pasted or OCR'd) did not match: the lead-in stripper removes at most four «حدثنا … قال» links and the six-narrator isnad left the query longer than the matn — new `isnad_matn` (diacritic-tolerant, finds the last «ﷺ قال/يقول») adds the matn as a candidate span; attribution markers in `quotes.py` are now diacritic-tolerant and include «سمعت رسول الله».
- Tesseract fallback emitted junk lines from the diacritics band of vocalised text and dropped stand-alone quote marks — junk lines (mostly 1–2-letter fragments plus stray digits) are removed before pass selection, quote marks are kept, and «صل الله عليه وسلم» (a common OCR rendering) is recognised as the honorific.
- Result on the user's screenshot: vision path → verified 96% Bukhari 1; Tesseract path → partial 86% Bukhari 1 with the four misread letters highlighted. Covered by unit tests built from both real transcriptions, an integration test (ai=0 and ai=1) and an e2e scenario in both languages. Benchmark unchanged at 97%.

## Alignment with the challenge's reference table

- Hadith: rulings of every scholar are now fetched from الدرر السنية (dorar.net/hadith search cards: الراوي، المحدث، المصدر، الرقم، خلاصة الحكم) for the matched hadith, using the source record's wording (never the user's text), ranked by same book/number, shown verbatim in a new card, and cached in a `source_cache` table that is part of the retrieval corpus.
- Extended explanation: was written from the model's general knowledge — it is now RAG over the approved reference: the hadith's شرح (`/hadith/explain/{id}`) or the verse's موسوعة التفسير section (`/tafseer/{surah}/{n}`), with the source link shown; no source → no extended text.
- Qur'an: English translation switched from Saheeh International to Hilali & Khan (King Fahd Complex edition, via QuranEnc), verse links to quranpedia.net, grader label «مصحف المدينة النبوية — مجمع الملك فهد». The Qur'an's role (detecting a verse quoted as a hadith) is stated in the README and on the Sources page.
- Glossary: linked to «الجمهرة» entries (5/10 found with an exact, hamza-preserving title match; «الأيمان» (oaths) is no longer mistaken for «الإيمان»).
- "Any language": was untrue (French/Indonesian/Urdu/Turkish abstained) — other languages are now machine-translated to English for matching only, labelled in the report, never graded as the user's translation; without a provider the app abstains with a clear reason.
- Sources page and both READMEs rewritten to state each source's role, including the sunnah.com-derived open dataset used as the matching index.
- Verification: 74 unit, 37 integration, 55 browser scenarios × 3 consecutive green runs; benchmark 97%; 0 5xx.

## Deployment, reliability and evaluation round

- **Deployment:** API and database on an Oracle Cloud Always Free VM (docker compose, Caddy with an automatic certificate on an sslip.io hostname), site on Cloudflare Pages, automatic deploy after green CI. Fixed on the way: HNSW index build failed on Docker's 64 MB `/dev/shm` (`shm_size: 1gb`); Pages uploads landed as previews because the checkout is a detached commit (`--branch=main`); the frontend job now waits for `API_URL`. Nightly `pg_dump` (7 kept) and a 30-minute uptime workflow added.
- **Duplicate rulings:** الدرر search pages repeat entries, so the same ruling was shown twice. Cards are now de-duplicated by scholar, book, number and text, including those already in the cache.
- **Brief explanation said a hadith is a foundation «في الشعر والدين»:** the prompt now forbids commentary. Code checks catch a grade that contradicts the record, a verdict while abstaining, and numbers absent from the facts. A second model pass flags unsupported claims. After one rewrite, a fixed template built from the facts is used.
- **Wrong number in the explanation facts for curated sayings:** the internal list number (2) was sent instead of the reference number (السلسلة الضعيفة 416). The facts now carry the ruling's number.
- **"(peace be upon him)" taken as the quote:** an English paraphrase was attributed to an unrelated record that contains those words. Honorific-only and reference-only spans are dropped, English parentheses are not quotations, and a short typed text competes with its fragments.
- **Cross-reference records («بمثله», «فذكر نحوه») matched:** they carry no text of their own and are excluded from matching and narrations.
- **Short quote with a missing word confirmed against a different hadith** (circulated set, «خير الأمور أوسطها» → «… وشر الأمور محدثاتها», shown as authentic). An Arabic quote of four content words or fewer must now contain every one of them, or it is at most the closest text. The rule only demotes.
- **Narrations:** the same text in other books or under other numbers is listed with each record's ruling. The corpus benchmark moved from 97% to 98% strict and 100% same hadith, because the three earlier "wrong attributions" were the same hadith elsewhere.
- **Retrieve-then-verify for English and translated input:** a model compares the input with the top records. A light fallback model confirmed a Qur'an verse for a hadith narrative, so only a strong model (Groq gpt-oss-120b, or Anthropic) may raise a record now, a verse is never raised, and any model may reject.
- **Multilingual claim corrected:** the earlier "French 95%" came from a few famous hadiths. A reproducible 90-item paraphrase set replaced it, with a hand-reviewed list of parallel narrations. Final run, paced for the free tiers so the strong judge stayed available: 31% confirmed the right hadith, 56 abstained or closest text only, 3 of 90 attributed to another hadith (each a different incident on the same topic).
- **Embedding model test:** multilingual-e5-large against MiniLM on the English queries gave recall@1 3% against 8% and recall@10 33% for both. MiniLM stays.
- **New evaluation:** a circulated-texts set of 50 sayings from social media, labelled from الدرر rulings (quoted per item). Result: 21/21 authentic confirmed, 22/25 weak or fabricated flagged or abstained, 0 dangerous errors.
- **PDF export** replaced "copy report". The first PDF clipped the page edge and left large gaps; the print layout now pads the content and lets long lists break between items.
- **Share image:** desktop Chrome opened the system share sheet, which never returns under automation, so phones now share and computers download.
- **Accessibility:** axe-core found contrast failures on English screens (white on the violet button was 4.0:1, and a grey note). The button and notes were darkened, and all 10 screens now pass WCAG 2.1 AA. Phone-size tests were added.
- **Lint:** five "setState in effect" errors were fixed with `useSyncExternalStore` and state created from storage. CI now runs the frontend lint and lints the eval scripts.
- **English precision rules (from the multilingual review):** a wording match must also agree in meaning (meaning score at least 60), because generic English words appear everywhere. A match that rests on meaning alone is attributed only when a strong model confirms it is the same report; otherwise it is the closest text. The three remaining attributions to another hadith (a garbled input, a zakat story, an Urdu story matched to a verse) now abstain.
- **Verification:** 113 unit tests, 37 integration checks, 71 browser tests (57 scenarios, 10 accessibility, 4 phones). Two browser runs failed while the machine slept and the free model quota was exhausted; both passed on rerun.

## Assistant and curated sayings round

- **Curated sayings 12 → 68:** `ingest/build_seed_from_dorar.py` labels each candidate from الدرر. Found and fixed while building it:
  - Weak rulings that contain the word «صحيح» only in negation («ليس له إسناد ثابت», «معناه صحيح لكن…») were read as authentic. A negation-aware reader fixed that.
  - «استعينوا على قضاء حوائجكم بالكتمان» would have been added as weak although الألباني graded a variant «جيد». Authentic rulings on variant wordings are now searched through الدرر's own authentic-only filter, and they block a saying.
  - Narrator descriptions such as «رجاله رجال الصحيح» are treated as neutral, not as a ruling.
- **Green state for a curated saying:** «النظافة من الإيمان» showed "confirmed" next to «ليس بصحيح». The weak-ruling detector now reads «ليس بصحيح», «ليس بحديث», «لم يثبت», «غير محفوظ», «ضعف» and similar, and a test checks every curated saying.
- **Assistant routing:** «هل يصح حديث …» was routed to fatwa because the fatwa pattern reads «هل يصح» as "is it permissible". A message that names a hadith with a text to check now goes to verification. Explicit legal questions such as «ما حكم …» and «هل يجوز …» go to referral.
- **Knowledge-base retrieval:** «ما مصادر الأداة؟» retrieved the general "what the tool does" section. Section keywords, separate Arabic and English embeddings and a keyword boost fixed it.
- **Voice on silence:** with a hint prompt, Whisper echoed the prompt back on silent audio with moderate confidence. The prompt was removed, and the browser now refuses recordings with less than half a second of audible sound before anything is uploaded.
- **Browser microphone in tests:** Chrome's fake microphone hangs on this Mac, so the tests provide a generated audio stream through `getUserMedia`.
- **Voice benchmark:** Arabic 20/20 recordings led to the right hadith, with a median word error rate of 10%. English 9/10, median 5%. Silence, French and noise were 3/3 refused. The benchmark first hit the assistant's own per-user limit after 20 recordings. Running directly against the API, it now uses a distinct client address per item; behind Caddy that address comes from the real client.

## Sanad: spoken conversation round

- **Inaccurate voice answer (user report):** «قال رسول الله ﷺ إنما الأعمال بالنيات…» was transcribed as «ورحمة الله صلى الله عليه وسلم إنما الأعمال بالنيات وإنما لكل مرء مهنوة». The broken opening was not recognised as an attribution, so the result was "uncertain" at 74. Text before an early «صلى الله عليه وسلم» is now treated as the attribution, and the same input gives "partial" for Bukhari 1.
- **Person-like conversation (user request):** the assistant is now Sanad (سند). It greets aloud, makes small talk and holds a spoken conversation: it listens with end-of-speech detection, reads back a heard hadith, waits for a spoken «نعم» or «لا», answers in a natural voice and listens again.
- **Small talk was taken as a text to verify:** «الحمد لله بخير» routed to verification, because any Arabic text of three words or more without a question did. Small-talk patterns now come first.
- **Voice choice:** Groq's Saudi Arabic Orpheus voice needs a one-time terms acceptance in the Groq console. Gemini TTS works on the free key, with latency about two thirds of the audio length, so replies are spoken sentence by sentence.
- **Sanad mispronounced the end of replies (user report):** the free Gemini voice allows 10 requests a day. After a few sentences it returned 429, and the rest of the reply fell back to the device's Arabic voice. Fix: Piper is self-hosted on the server as the default voice, with no quota and about 0.2 to 0.9 s per sentence. Transcribing its output with Whisper recovered nearly every word. Numbers are now read as Arabic words.
- **API key in the server log:** the Gemini voice request carried the key in its URL, which the HTTP client logged. The key now travels in a header.
- **Voice accuracy (user report, «امرئ» transcribed «مرئ»):** the error types were measured on the 20 Arabic recordings: split or joined words, dropped endings, a missing initial alef or «ال». A hint prompt was tested and gave no clear gain, so it stays off. A corpus-aware spelling correction now runs on Arabic transcripts that match a source at 80 or more. It uses the source's spelling only where the two differ in spelling alone, so «بالنية», a real narration, is never changed. The raw transcript is shown as "as heard". Word error rate fell from 10% to 0% median and 5% mean, with 13 of 20 transcripts perfect and 20/20 still the right hadith.

## Same hadith, other languages, and the review form round

- **English gave a weaker result than Arabic for the same hadith (user report, Bukhari 61):** the Arabic paste was verified at 94, but the English paste from sunnah.com was "uncertain" at 60. The English index keeps only the Prophet's quoted words, while people paste the whole translation with the narrator line and the story, so the wording score was 54. The English text is now also compared like for like: its own quoted words against the index, and the full text against the record's full English. A whole typed text of up to 1,500 characters now competes with its fragments (it was 400). Result: Bukhari 61 in English is verified at 95. A new benchmark of 40 full English pastes went from 34/40 to **40/40**. The corpus set stayed at 100% same hadith, and the circulated set at 0 dangerous errors.
- **Other languages (same report):** 39 full translations (French, Indonesian, Urdu, Turkish) gave 26/39 right hadith, with 0 attributed to a different hadith. The two "other" records were the same saying of Anas in other chapters of al-Bukhari.
- **Free quotas used up by benchmarks:** during that run, Groq's daily token quota (200,000) ran out. The match check fell back to the light Gemini model, which may not raise a match, so meaning-only matches stayed at "closest text". The benchmarks also used up Gemini's free 500 requests for the day. The live site shares these keys. Changes:
  - Groq's smaller `gpt-oss-20b` (its own quota) is now the last fallback.
  - The match check sends English only (872 → 587 prompt tokens on a typical check) and reuses a verdict for the same text.
  - TECHNICAL.md now lists every free quota and what each action costs.
  - Lesson: benchmarks need their own keys.
- **Human-review form (user request):** the review button now asks for a name and email. The server renders its own report as a PDF (WeasyPrint, Amiri font, right to left in Arabic). The request then goes to the team's inbox through the Web3Forms contact form. Web3Forms' free plan accepts browser submissions only and has no attachments (both are paid features), so the message carries a private PDF link, kept 14 days. Only reports the server produced are rendered, so a PDF cannot carry a verdict the tool did not give. Tests mock the form, so no real emails are sent.
- **Review form follow-up (user report):**
  - The dialog opened at the right edge, not the centre. The CSS reset sets every margin to 0, which removes the `margin: auto` that centres a modal dialog. Restored.
  - The emailed PDF looked different from the export PDF, because it came from a separate template. The server now prints the site's own result page with a headless Chromium, in the person's time zone, so it is the same document as the export button. Removing the template also means the name and email no longer reach the API: they go to the contact form only.
- **Arabic screenshot read badly (user report):** the server log showed Gemini and OpenRouter out of their free daily quota at that moment, so the image went to Tesseract, which garbles vocalised Arabic («الأغمال», «مِجْرَا خرّنَهُ» for «هجرته»). Gemini itself reads such images well. Six Gemini models were tried on the user's sunnah.com screenshot: `gemini-3.1-flash-lite` read it word for word in 5.6 s, on its own free quota. It now follows the first Gemini model in the chain. The same screenshot and the test fixture are read exactly, and both give Bukhari 1.
