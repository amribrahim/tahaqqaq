# تحقّق — Tahaqqaq

Verify a hadith before you publish it. Built for the **AI Challenge Serving Islamic Content 2026** (hadith track).
[النسخة العربية ← README.ar.md](README.ar.md) · **Live:** https://tahaqqaq.pages.dev · **How it is built:** [TECHNICAL.md](TECHNICAL.md)

**Principle:** the tool *relays* the scholars' rulings from approved sources. It never issues a verdict of its own, and when no reliable match exists it says so and abstains.

## What it does

- **Input:** text (Arabic and English are matched directly; any other language is machine-translated to English *for matching only* and labelled as such), a **screenshot** of a post (vision-model transcription with Tesseract/OpenCV fallback), or a **link** (public articles, sunnah.com pages, X posts).
- **Result states:** مؤيَّد بمصدر (confirmed) · مؤيَّد جزئيًا – اختلاف رواية (variant wording) · غير مؤكد (closest text only) · وُجد النص وحكمه موضوع/ضعيف (found, fabricated/weak) · لا مرجع – يُمتنع (abstain) · إحالة (personal fatwa question → referred to scholars).
- **Report:** the ruling *verbatim* with grader, book, number and links; **every scholar's ruling from الدرر السنية** for the matched hadith; **the same report in other books** (its narrations), each with its own recorded ruling; a word-level diff against the correct wording; translation accuracy for English input; glossary notes for terms that must not be translated literally.
- **Share and keep:** export the report as a **PDF** (Arabic or English), or as an **image to share** that carries the recorded ruling, its source and the disclaimer, ready to post as a correction.
- **AI explanation:** brief, or extended (شرح موسّع) in 25 languages. The extended text is **summarised only from the hadith's شرح or the verse's tafsir at الدرر السنية**; when none exists, nothing is shown.

## Sources, and what each one is used for

The challenge's reference table lists the approved content per field. The app is a **hadith** tool; it also uses the Qur'an for one purpose (detecting a verse quoted as a hadith) and the glossary for translation notes.

| Approved reference (challenge table) | Used for | How |
|---|---|---|
| **الموسوعة الحديثية — dorar.net/hadith** (Hadith) | Rulings of the scholars and the hadith's شرح | Fetched live for the matched hadith, shown verbatim with links, cached in `source_cache` |
| **Sahih al-Bukhari, Sahih Muslim, the four Sunan** (Hadith) | Text matching | Sahihayn: ruling = the compiler's inclusion. Sunan: a hadith is attributed **only** with a recorded editor's ruling |
| **Madinah Mushaf — King Fahd Complex / quranpedia.net** (Qur'an) | Detecting a verse quoted as a hadith; correcting misquoted verses | Uthmani text, surah/ayah, link to quranpedia.net; English: **Hilali & Khan (King Fahd Complex edition)** |
| **موسوعة التفسير — dorar.net/tafseer** (Tafsir) | Extended explanation of a verse | Summarised from the tafsir section text only |
| **الجمهرة — islamic-content.com** (Da'wa content) | Definitions of terms of art | Entry text and link for 5 of the 10 glossary terms; the rest keep reviewed seed text |
| Aqeedah (dorar.net/aqeeda) | Not used | The tool answers no creed questions; personal religious questions are referred |

**Where the searchable texts come from (stated plainly):** the Six Books texts, their published English translations and the editors' grades are indexed from the open **hadith-api** dataset (CC0, derived from sunnah.com). It is the matching index; the approved reference for rulings is الدرر السنية, shown next to every hadith result. The Qur'an text is the Madinah Mushaf Uthmani text (fetched through the Quran.com API).

**What the database holds (the retrieval corpus):** 34,153 hadiths · 6,236 verses · 12 circulated sayings with their rulings · 10 glossary terms · a growing `source_cache` of الدرر rulings, شروح and tafsir sections. User input is never stored.

## Is it RAG?

Yes, constrained:

| Step | AI | Guardrail |
|---|---|---|
| Retrieval | Multilingual embeddings (pgvector) + trigram similarity (pg_trgm) over the corpus above | Explicit cascade: exact → trigram → semantic (needs shared wording) → abstain |
| Ruling | **None** | Read verbatim from the source record; no attribution without a recorded ruling |
| Extended explanation | LLM summarises the **retrieved** شرح/tafsir from الدرر السنية | Source text is the only input; the source link is shown; no source → no text |
| Brief explanation | LLM words the fixed facts (ruling, source, state) | Labelled «شرح مولَّد بالذكاء الاصطناعي»; checked by code (no contradicting grade, no invented numbers, no verdict when abstaining) and by a second model pass (no claims the facts do not support); otherwise a fixed template built from the facts |
| Match check | For English or translated input, a model compares the input with the top records: same report or not | Only a strong model may confirm, and only up to "partial"; any model may reject (→ closest text only); a Qur'an verse is never raised; a match that rests on meaning rather than shared wording is attributed only when confirmed |
| Images, links, long text | Vision transcription; extraction of quoted segments | Every segment must exist literally in the input |
| Other languages | Machine translation to English, for matching only | Labelled in the report; never graded as the user's translation |

LLM providers: Gemini → Groq → OpenRouter (free tiers) or Claude, behind one OpenAI-compatible client with automatic fallback (`LLM_PROVIDER`, `LLM_FALLBACKS`). Without a provider every verification feature still works except the explanation, image transcription by a model (Tesseract is used) and other-language input.

## Measured accuracy

Three benchmarks in [`backend/eval`](backend/eval), run against the live API:

| Set | What it is | Result |
|---|---|---|
| Corpus set (98 inputs, fixed seed) | Exact and variant quotes of Sahihayn hadiths, fabricated/weak sayings, exact and misquoted verses, invented texts, fatwa questions | **100%** right hadith (98% the exact labelled number); **0** attributions to another hadith; **6/6** invented texts abstain; median latency ~0.3 s |
| Circulated texts (50 sayings, 46 scored) | Sayings that circulate on social media as hadiths; each label decided from الدرر السنية rulings, quoted per item | Authentic: **21/21** confirmed. Weak, fabricated or not a hadith: **22/25** flagged with their ruling or abstained, 3 shown only as the closest text. **0 dangerous errors** (nothing fabricated shown as authentic, nothing authentic shown as weak) |
| Multilingual paraphrases (90 inputs) | Authentic hadiths rewritten loosely by a model in French, Indonesian, Urdu, Turkish and English | **31%** confirmed the right hadith (French 28%, Indonesian 39%, Urdu 33%, Turkish 33%, English 22%); 56 abstained or shown only as the closest text; **3 of 90** attributed to another hadith, each a different incident on the same topic. Measured with the free model check available; when its quota is exhausted, matches on meaning alone fall back to the closest text |

"Right hadith" counts the labelled record, a record whose narrations include it, or a parallel narration confirmed by hand review ([`multilingual_equivalents.json`](backend/eval/multilingual_equivalents.json)). The embedding model was also tested against a ten-times-larger one (multilingual-e5-large); it gave no gain, so the small model stays ([TECHNICAL.md §9](TECHNICAL.md#9-retrieval-cascade-and-scoring)).

## Run locally

```bash
cp .env.example .env                 # LLM keys are optional
docker compose up -d db api web
docker compose run --rm ingest       # once: download, index and link the sources (~40 min)
open http://localhost:3000
```

Re-runnable ingestion steps: `ingest.ingest_hadith`, `ingest.ingest_quran`, `ingest.quran_kfgqpc` (King Fahd Complex translation + quranpedia links), `ingest.ingest_seed_rulings`, `ingest.ingest_glossary`, `ingest.enrich_glossary` (الجمهرة), `ingest.renormalize`, `ingest.reembed_en`.

## Tests

```bash
cd backend && .venv/bin/pytest -q                                  # 113 unit tests (offline, real fixtures)
docker compose --profile qa up -d db api web fixtures
cd backend && TAHQAQ_STACK=1 .venv/bin/pytest tests/integration -q   # 37 checks against the running stack
cd frontend && npx playwright test                                 # 71 browser tests: 57 scenarios in Arabic and English,
                                                                   # 10 accessibility audits (axe-core, WCAG 2.1 AA), 4 phone-size runs
```

Every failure found and fixed is recorded in [`QA_LOG.md`](QA_LOG.md). Test fixtures, screenshots and the benchmark report are generated into a local `qa/` folder, which is not published.

## Deploy

- **Backend:** an Oracle Cloud Always Free Arm VM runs `docker-compose.prod.yml` (Postgres + API). Caddy serves the API over HTTPS at `https://<ip-with-dashes>.sslip.io` with an automatic Let's Encrypt certificate; Postgres is never exposed.
- **Frontend:** Cloudflare Pages (static export).
- **Automatic deploy:** after CI passes on `main`, `.github/workflows/deploy.yml` connects over SSH, resets `/opt/tahaqqaq` to the pushed commit, rebuilds and waits for `/health`.
- **Repository secrets:** `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY`, `SSH_KNOWN_HOSTS`. Add `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` for Pages.
- **Repository variables:** `DEPLOY_ENABLED=true`. Add `CF_PAGES_PROJECT` and `API_URL` for Pages.
- **Server-only settings:** the model keys, `POSTGRES_PASSWORD` and `API_HOST` live in `/opt/tahaqqaq/.env`, never in git. The database is restored once from a `pg_dump` of a local ingest.

- **Backups and monitoring:** a nightly `pg_dump` on the server keeps the last 7 days (`deploy/backup.sh`); `uptime.yml` checks the site, the API and a real verification every 30 minutes and e-mails on failure.

CI (`ci.yml`) runs lint, unit tests, type-check and the production build on every push.

## Known limits

- الدرر rulings are found by searching the matched hadith's text; entries with the same book and number are ranked first. Shamela is not used.
- The curated list of circulated sayings is small and should be reviewed by a specialist before launch.
- Instagram, Facebook, YouTube and TikTok links cannot be read; paste the text or a screenshot.
- The embedding model (multilingual MiniLM) is weak on long Arabic passages, so retrieval uses short windows and wording decides.
- Loosely paraphrased input in other languages often abstains: the tool prefers no answer to a wrong attribution.
- The curated list of circulated sayings, the circulated-texts labels and the parallel-narration review were prepared by the developer from الدرر rulings, not by a hadith specialist; a specialist review comes before a public launch.

## Repository layout

```
design/      exported UI design (source of truth for layout, colours, copy)
frontend/    Next.js app (static export), Playwright e2e
backend/     FastAPI app, ingestion, evaluation set, tests
```
