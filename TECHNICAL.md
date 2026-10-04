# Tahaqqaq (تحقّق) — technical documentation

This document explains how the system is built and how it works, end to end: the technology stack, the infrastructure,
where every piece of data comes from, how a verification runs, where AI is used and how it is controlled, and how
quality is measured. It is written for engineers, reviewers and judges who want to understand or rebuild the system.

For what the product does and how to run it, see [README.md](README.md) / [README.ar.md](README.ar.md).

## Contents

1. [Purpose and the one rule](#1-purpose-and-the-one-rule)
2. [Architecture at a glance](#2-architecture-at-a-glance)
3. [Technology stack](#3-technology-stack)
4. [Infrastructure and deployment](#4-infrastructure-and-deployment)
5. [Data: sources and how each one is obtained](#5-data-sources-and-how-each-one-is-obtained)
6. [Database](#6-database)
7. [Ingestion](#7-ingestion)
8. [A verification, step by step](#8-a-verification-step-by-step)
9. [Retrieval cascade and scoring](#9-retrieval-cascade-and-scoring)
10. [RAG: the extended explanation](#10-rag-the-extended-explanation)
11. [AI components and how they are controlled](#11-ai-components-and-how-they-are-controlled)
    - [11a. The assistant](#11a-the-assistant)
12. [API reference](#12-api-reference)
13. [Frontend](#13-frontend)
14. [Quality: tests and benchmarks](#14-quality-tests-and-benchmarks)
15. [Security and privacy](#15-security-and-privacy)
16. [Configuration reference](#16-configuration-reference)
17. [Known limits](#17-known-limits)
18. [Repository layout](#18-repository-layout)

---

## 1. Purpose and the one rule

People share sayings attributed to the Prophet ﷺ without checking them. Tahaqqaq takes a text, a screenshot or a link,
finds the saying in approved sources, and reports **the ruling that scholars recorded for it, verbatim**, with the
source, number and links.

The one rule that shapes the whole design: **the tool never issues a ruling of its own.** No model grades a hadith.
A ruling is shown only when it exists in the data next to a matched source record ("لا يُنسب حديث دون مصدر وحكم
معتمد في البيانات"). When there is no reliable match, the tool abstains and says so.

## 2. Architecture at a glance

```mermaid
flowchart LR
  U[Browser] -->|static pages| CF[Cloudflare Pages<br/>Next.js static export]
  U -->|HTTPS JSON / SSE| CA[Caddy<br/>TLS, Let's Encrypt]
  subgraph VM[Oracle Cloud VM · Always Free · Arm 2 OCPU / 12 GB · docker compose]
    CA --> API[FastAPI pipeline]
    API --> PG[(PostgreSQL 16<br/>pgvector + pg_trgm)]
    API --> EMB[fastembed MiniLM<br/>local, CPU]
    API --> OCR[OpenCV + Tesseract<br/>OCR fallback]
  end
  API -->|rulings, sharh, tafsir| DORAR[dorar.net<br/>cached in source_cache]
  API -->|bounded calls, JSON| LLM[LLM provider chain<br/>Gemini → Groq → OpenRouter]
  GH[GitHub Actions] -->|CI, then deploy over SSH| VM
  GH -->|wrangler| CF
```

- The **frontend** is a static site. It holds no secrets and talks only to the API.
- The **API** runs the whole verification pipeline. The database holds the searchable corpus. Embeddings are computed
  on the server's CPU, with no external embedding service.
- **الدرر السنية** (dorar.net) is fetched live for rulings, شرح and tafsir, and cached in the database.
- **LLMs** are optional helpers in clearly bounded steps (section 11). Without any provider configured, every
  verification feature still works except the explanations, model-based image transcription and other-language input.

## 3. Technology stack

| Layer | Technology | Why |
|---|---|---|
| Frontend | Next.js 16 (App Router, static export), React 19, TypeScript, Tailwind CSS 4, shadcn/ui primitives | Static pages are free to host on a CDN and fast everywhere |
| i18n | next-intl, Arabic (RTL, default) and English (LTR) | Arabic-first product with a full English mode |
| Fonts | Cairo (headings) and Tajawal (text) via next/font | Good Arabic shaping in the browser, the PDF and the share image |
| API | Python 3.12, FastAPI, Pydantic v2, Uvicorn | Typed request/response models, streaming progress (SSE) |
| Database | PostgreSQL 16 with pgvector (HNSW) and pg_trgm (GIN) | One store for exact, fuzzy and semantic search |
| Embeddings | fastembed (ONNX) `paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensions | Runs on CPU, multilingual (Arabic and English), no API cost |
| Fuzzy matching | rapidfuzz | Word-level and character-level similarity for rescoring |
| OCR fallback | OpenCV (deskew, binarise, upscale) and Tesseract `ara+eng` with tessdata_best | Works without any model |
| Link reading | trafilatura → readability-lxml → densest text block; fxtwitter JSON for X posts; a sunnah.com page parser | Extracts the article text from a page |
| Speech to text | Whisper large-v3 on Groq (same key as the text models) | Arabic and English voice input for the assistant, with confidence data per segment |
| Text to speech | Piper (self-hosted, MIT) with Arabic and English voices; Groq Orpheus optional | Sanad's voice with no quota; correct Arabic vowels through automatic diacritisation |
| LLM access | One OpenAI-compatible HTTP client with a provider chain (Gemini, Groq, OpenRouter; Anthropic optional) | Free tiers, automatic fallback on rate limits |
| Reverse proxy | Caddy 2 | Automatic HTTPS certificates |
| Containers | Docker Compose (dev and prod files) | One command to run the stack |
| CI/CD | GitHub Actions (CI, deploy, uptime) and Wrangler for Cloudflare Pages | Every push is tested, then deployed |
| Tests | pytest, Playwright with installed Chrome, axe-core | Unit, integration, browser, accessibility and phone tests |

## 4. Infrastructure and deployment

**Hosting (all free tiers):**

| Part | Where | Notes |
|---|---|---|
| Frontend | Cloudflare Pages, project `tahaqqaq` → https://tahaqqaq.pages.dev | Static export (`frontend/out`), built in GitHub Actions |
| API + database | Oracle Cloud Always Free VM: VM.Standard.A1.Flex, 2 OCPU / 12 GB RAM, Oracle Linux 9 (aarch64) | `docker-compose.prod.yml`: `db`, `api`, `caddy` |
| HTTPS for the API | Caddy with a Let's Encrypt certificate for `<ip-with-dashes>.sslip.io` | sslip.io maps the hostname to the IP; no domain purchase needed |

**Production compose** (`docker-compose.prod.yml`):

- `db`: `pgvector/pgvector:pg16`, tuned for 12 GB (`shared_buffers=2GB`, `effective_cache_size=6GB`,
  `maintenance_work_mem=512MB`), `shm_size: 1gb` because parallel HNSW index builds need more than Docker's 64 MB.
  Not published on any port.
- `api`: built from `backend/Dockerfile`. It listens on `127.0.0.1:8000` only, for health checks on the machine.
- `caddy`: publishes 80/443 and reverse-proxies to `api:8000` (`deploy/Caddyfile`). It streams Server-Sent Events
  unbuffered, which the progress stream needs.
- Secrets and settings live in `/opt/tahaqqaq/.env` on the server (`chmod 600`), never in git: model keys,
  `POSTGRES_PASSWORD`, `CORS_ORIGINS`, `API_HOST`.

**Network:** the Oracle security list allows 22 (SSH), 80 and 443. The VM firewall (firewalld) allows the same.
Postgres is never reachable from outside.

**CI/CD** (`.github/workflows/`):

| Workflow | Trigger | What it does |
|---|---|---|
| `ci.yml` | every push and pull request | Backend: ruff lint and the unit tests. Frontend: lint, type-check and the production build. |
| `deploy.yml` | after CI succeeds on `main`, or by hand | 1) SSH to the VM, `git reset --hard <sha>`, `docker compose up -d --build`, wait for `/health`, print logs on failure. 2) Build the static site with `NEXT_PUBLIC_API_URL` and publish it with Wrangler as the production branch. |
| `uptime.yml` | every 30 minutes | Calls `/health` (database connected), runs a real verification and loads the site. A failure is e-mailed by GitHub. |

Repository settings for deployment: secrets `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY`, `SSH_KNOWN_HOSTS`,
`CLOUDFLARE_API_TOKEN` (Pages edit), `CLOUDFLARE_ACCOUNT_ID`; variables `DEPLOY_ENABLED=true`, `CF_PAGES_PROJECT`,
`API_URL`.

**Backups:** `deploy/backup.sh` runs nightly from cron on the VM. It runs `pg_dump -Fc`, about 400 MB in about 75 seconds,
and keeps the newest 7 dumps in `/opt/tahaqqaq/backups`. The corpus can also be rebuilt from the public sources with
the ingestion scripts. The dump saves that time and keeps the الدرر cache.

**First-time setup of a server** (done once): install Docker, clone the repo to `/opt/tahaqqaq`, write `.env`, restore
the database from a `pg_dump` of a local ingest (`pg_restore` into the `db` container), build the HNSW indexes, start
the stack. After that, every push deploys automatically.

## 5. Data: sources and how each one is obtained

The challenge's reference table defines the approved content for each field. The table below lists every dataset the
system uses, where it comes from and what it is used for.

| Data | Source | Licence / status | How it is obtained | What is stored | Used for |
|---|---|---|---|---|---|
| The Six Books: Arabic text, matn, English translation, editors' grades | **hadith-api** dataset by fawazahmed0 (derived from sunnah.com) | CC0 | `ingest/ingest_hadith.py` downloads the JSON editions | 34,153 records in `texts` (kind `hadith`), grades **verbatim** in `grades` | The searchable matching index |
| Rulings of Sahih al-Bukhari and Sahih Muslim | The compiler's inclusion, as الدرر records it («المحدث: البخاري · المصدر: صحيح البخاري · صحيح») | — | Set at ingestion for the two Sahihs | In `grades` | The ruling shown for Sahihayn matches |
| Scholars' rulings and شرح of the matched hadith | **الموسوعة الحديثية — dorar.net/hadith** (approved) | Public website | `app/dorar.py`: `/hadith/search` result cards and `/hadith/explain/{id}` pages, fetched live and parsed | `source_cache` rows, keyed by query | The rulings card and the extended explanation |
| Qur'an text | **Madinah Mushaf** Uthmani script (King Fahd Complex standard) via the Quran.com v4 API | Public API | `ingest/ingest_quran.py` | 6,236 verses (kind `quran`) | Detecting a verse quoted as a hadith, correcting misquoted verses |
| Qur'an English translation and links | **Hilali & Khan** («The Noble Qur'an», King Fahd Complex edition) via the QuranEnc API; **quranpedia.net** links | Public API / website | `ingest/quran_kfgqpc.py` | `text_en`, `source_url` | Showing a verse in English, the source link |
| Tafsir | **موسوعة التفسير — dorar.net/tafseer** (approved) | Public website | `app/dorar.py`: the section of the surah that covers the verse | `source_cache` | The extended explanation of a verse |
| Glossary of terms of art | Seed list of 10 terms (`ingest/seeds/glossary.csv`), enriched from **الجمهرة — islamic-content.com** (approved) | Public website | `ingest/ingest_glossary.py`, `ingest/enrich_glossary.py` | `glossary`; 5 of 10 terms carry the الجمهرة text and link | Translation notes («Taqwa» is not "fear») |
| Circulated sayings outside the Six Books | Curated seed (`ingest/seeds/rulings_seed.json`): 68 sayings, each with rulings quoted verbatim from الدرر. 12 were entered by hand; 56 were added by `ingest/build_seed_from_dorar.py` (see below) | — | `ingest/ingest_seed_rulings.py` | 68 records (kind `seed`) | Flagging famous fabricated or weak sayings with their ruling |

**How the curated sayings are grown** (`ingest/build_seed_from_dorar.py`): the developer lists candidate sayings that
circulate as hadiths (`ingest/seeds/circulated_candidates.txt`). For each one the script searches الدرر and keeps it
only when:

1. a matching entry records a weak, fabricated or baseless ruling, and
2. no entry records an authentic one. This is checked on the saying itself and on variant wordings, using الدرر's
   own authentic-only filter (`d[]=1`) as well as the plain search.

Contested sayings stay out. For example «استعينوا على قضاء حوائجكم بالكتمان» was rejected because الألباني graded a
variant «جيد». Every decision, with the quoted rulings, is written to `ingest/seeds/seed_review.md` for a specialist's
review. Of 142 candidates, 56 were added. Every saying's first ruling must resolve to a weak state, and a unit test
enforces it.

**What is never stored:** user input. Texts, images and links are processed in memory and dropped after the response.
The recent-checks list lives in the browser's `sessionStorage` only. The one exception is a **human-review request**
the person sends with their name and email: the report PDF is then kept for 14 days so the reviewer can open it (see
[the API reference](#12-api-reference)). Reports stay in the API's memory for up to six hours, so that a review request
renders exactly the report the person saw.

**Not used:** المكتبة الشاملة, and dorar.net/aqeeda. The tool answers no creed questions, and personal religious
questions are referred to scholars.

## 6. Database

PostgreSQL 16 with two extensions: `vector` (pgvector) and `pg_trgm`. Schema in `backend/app/db.py`.

| Table | Rows | Purpose |
|---|---|---|
| `texts` | 40,457 | One row per hadith, verse or seed saying: `kind`, `collection`, `number`, `book_*`, `chapter_*`, `text_ar` (with isnad), `matn_ar` (the saying), `matn_norm` (matching key), `text_en`, `text_en_norm`, `grades` (JSONB, verbatim), `source_url`, `alt_url`, `meta` |
| `chunks` | 219,418 | Short word-window embeddings: `text_id`, `lang` (`ar`/`en`), `pos`, `embedding vector(384)` |
| `glossary` | 10 | Terms of art with meanings, literal renderings to avoid, notes and source URL |
| `source_cache` | grows | Fetched الدرر pages: `key`, `source`, `url`, `payload` (JSONB), `fetched_at` |
| `ingest_meta` | few | Ingestion bookkeeping |

**Indexes:** HNSW (`vector_cosine_ops`) on `chunks.embedding`, one partial index for Arabic and one for English;
GIN trigram indexes on `texts.matn_norm` and `texts.text_en_norm`; `(collection, number)` unique.

**Why short windows:** MiniLM embeds long Arabic passages poorly, and users quote fragments. Each text is embedded as
overlapping word windows (`app/chunking.py`), and a text's semantic score is its best window.

## 7. Ingestion

All steps are idempotent Python modules (`backend/ingest/`), run once with `docker compose run --rm ingest`
(about 40 minutes) or one by one:

1. `ingest_hadith`: the Six Books from hadith-api. It extracts the matn from the full text, keeps the published English
   translation and the grades verbatim.
2. `ingest_quran`: Uthmani text and surah/ayah numbers.
3. `quran_kfgqpc`: the Hilali & Khan translation and quranpedia links.
4. `ingest_seed_rulings`: curated circulated sayings with their quoted rulings.
5. `ingest_glossary` and `enrich_glossary`: terms, then الجمهرة definitions and links.
6. `renormalize`: recompute `matn_norm` with the current normaliser and re-embed changed Arabic windows.
7. `reembed_en`: recompute the English matching key and English windows.

**Normalisation** (`app/normalize.py`, `normalize_ar`) is the single function used for stored keys and for queries:
NFKC, remove tashkeel and tatweel, unify alef forms (آ أ إ ٱ → ا), ى → ي, ة → ه, ؤ → و, ئ → ي, Persian kaf and ya →
Arabic, Arabic-Indic digits → ASCII, drop punctuation and symbols, strip lead-ins such as «قال رسول الله ﷺ». English
uses `normalize_latin` (lowercase, ASCII letters, digits and apostrophes).

## 8. A verification, step by step

Entry points: `POST /api/verify` (JSON) and `POST /api/verify/stream` (the same pipeline with live progress events,
used by the site). The code is `backend/app/pipeline.py::run`.

1. **Input.** One of three modes:
   - Text: up to 2,000 characters.
   - Image: PNG or JPG up to 10 MB, sent first to `POST /api/ocr`. A vision model transcribes it, with OpenCV and
     Tesseract as the fallback. Junk lines are dropped and wrapped lines rejoined. The user reviews the text before
     verifying.
   - Link: X posts through the fxtwitter JSON API, sunnah.com pages by a dedicated parser, other pages through
     trafilatura.
2. **Language.** The text must be in the interface language: Arabic in the Arabic interface, English in the English one
   (`check_language` in `app/main.py`, before anything else runs). Anything else gets `422 wrong_language` with a clear
   message; it is never machine-translated, because a translation changes the wording the verdict rests on. The detector
   (`detect_script_language`) recognises every Arabic text and every published English translation in the corpus, and
   calls a text another language only on positive evidence: Urdu or Persian letters and words, or the function words and
   letters of French, Indonesian, Turkish, Spanish, German, Italian or Portuguese. English full of transliterated names
   stays English, and Arabic honorifics inside an English translation do not make it Arabic. The site shows the same
   check before sending, with a one-click switch of the interface. A sunnah.com link gives the Arabic text in the Arabic
   interface and its English translation in the English one.
3. **Guards.**
   - A personal fatwa question returns `referral` and stops.
   - A request to *write* a hadith returns `abstain`, with no retrieval and no model call.
4. **Finding the quote.** A paste may contain commentary, an attribution, a whole post or page. Candidate spans come from:
   - **rules** (`app/quotes.py`): text in «» "" “”, or after an attribution such as «قال رسول الله ﷺ» or "the Prophet
     said". English parentheses are ignored, because they hold asides like "(peace be upon him)". Spans made only of
     honorifics («صلى الله عليه وسلم», "PBUH") or source notes ("(Sahih Muslim 55)", «رواه البخاري») are dropped.
   - an **isnad parser** that cuts the chain of narrators off a full hadith.
   - the **AI extractor**, for long texts, images and links. Each span it returns must appear literally in the input.

   Each span is verified. For a short typed text, the whole text competes too. A fragment replaces it only when it is
   presented as a quotation and scores at least as high, or when it scores at least 10 points higher.
5. **Retrieval and scoring** (section 9): exact or substring, then trigram, then semantic, else abstain.
6. **Match check, for English and translated input** (section 11, the match checker). A strong model compares the input
   with the top records: same report or not. It can confirm, which raises a record to partial at most, or reject, which
   caps it at closest text only. An English match that rests on meaning rather than shared wording (lexical below 70)
   **must** be confirmed. Without a strong model's confirmation, because it said no, was unavailable or was
   rate-limited, it is shown only as the closest text.
7. **State.** Thresholds on the 0–100 confidence: `verified` ≥ 90, `partial` ≥ 75, `uncertain` ≥ 50 (shown as the
   closest text only, not an attribution), below 50 `abstain`. Two rules on top:
   - a Sunan record without a recorded grade is at most `uncertain`, since there is no attribution without a ruling;
   - a matched record whose ruling is weak or fabricated becomes `unreliable`. It is red and never shows a green check.
8. **Attribution.** The ruling is read verbatim from the record (`grades`), with grader, book, number and links.
   Added to it:
   - **Narrations:** the same text in other books or under other numbers, each with its own recorded ruling. Found by
     trigram probes at the start, middle and end of the text, then rescored. Cross-reference records («بمثله») are
     excluded.
   - A **word diff** against the correct wording, for Arabic input.
   - A **translation-accuracy card**, for English input against the published translation.
   - **Glossary notes** for terms that must not be translated literally.
9. **الدرر rulings.** The site asks `GET /api/dorar` for the matched hadith. The API searches الدرر by the matched text,
   ranks the compiler's own entry first, drops repeated entries and returns the rulings verbatim. Results are cached.
10. **Explanation.** It is labelled «شرح مولَّد بالذكاء الاصطناعي» (AI-generated explanation) and kept visually separate.
    It comes in two modes:
    - **Brief:** it words the fixed facts and is fact-checked (section 11).
    - **Extended:** RAG over the الدرر شرح or tafsir (section 10).

    It is available in 25 languages on request.

The response (`VerifyResponse` in `app/schemas.py`) carries the state, confidence, reason in Arabic and English,
source, grades, narrations, candidates, segments, diff, translation card, glossary notes, the match check (if any), the explanation and per-step timings.

## 9. Retrieval cascade and scoring

`backend/app/matcher.py::search`. Candidates come from three searches, are merged and then **rescored with both signals**:

| Signal | How |
|---|---|
| Exact | The normalised query equals a stored key or is contained in it (≥ 15 characters) |
| Trigram | `pg_trgm` `word_similarity(query, key)`, threshold 0.35 for candidates |
| Semantic | pgvector cosine to the best embedded window (HNSW), top 120 windows grouped by text |
| Lexical (rescoring) | 0.5 × character similarity of the best-aligned window + 0.5 × share of the query's content words found in it (rapidfuzz) |

**Confidence:** Arabic = 0.75 × lexical + 0.25 × semantic, because the source wording decides. English = 0.5 × lexical
+ 0.5 × semantic, because translations legitimately differ.

**Cascade (English):** admitted when wording and meaning agree (lexical ≥ 70 and scaled meaning ≥ 60), or when the
combined score reaches 75 on meaning alone. The meaning-only case is marked and needs the match checker's confirmation
(section 8, step 6).

**Cascade (Arabic):**

1. **Exact:** score at least 90.
2. **Trigram:** `word_similarity ≥ 0.60` and lexical ≥ 70, or lexical ≥ 80. Score 75–100.
3. **Semantic:** cosine ≥ 0.80 and lexical ≥ 45 and trigram ≥ 0.55. Score 50–74, closest text only.
4. Otherwise **abstain**, score below 50.

Extra rules:

- **Short quotes:** an Arabic quote of four content words or fewer must contain every one of them. «خير الأمور أوسطها»
  is not «… وشر الأمور محدثاتها», so such a record is at most the closest text.
- **Cross-references:** records whose whole text is a reference such as «بمثله» or «فذكر نحوه» are never a match.
- **English on meaning alone:** an English record admitted by score (meaning) rather than by wording (lexical below 70)
  is marked `meaning_only`. The pipeline shows it as an attribution only if a strong model confirms it is the same report.
- **Ties:** the Qur'an, then the Sahihayn, then the curated seed, then the Sunan.

**Embedding model choice, measured (4 October 2026):** multilingual-e5-large (1024 dimensions, ten times larger) was
evaluated against MiniLM on English paraphrases. Recall of the labelled record: top 1 was 3% for e5 against 8% for
MiniLM, top 5 was 25% against 26%, and top 10 was 33% for both. It brought no gain, so MiniLM stays. (The comparison
scripts were removed with the multilingual set they ran on, when input in other languages was dropped.)

## 10. RAG: the extended explanation

Yes, the system uses retrieval-augmented generation, in a constrained form, for the **extended explanation**:

1. **Retrieve.** For a hadith, `app/dorar.py` finds the matched hadith on الدرر and fetches its شرح page from the
   الموسوعة الحديثية. For a verse, it fetches the section of موسوعة التفسير that covers it. Both are cached in
   `source_cache`.
2. **Generate.** The model receives only the facts (state, ruling, source) and the retrieved source text. The prompt
   (`GROUNDED_SYSTEM`) says to summarise *only* that text, in the requested language.
3. **Show.** The summary appears with a link to the exact source page.
4. **No source, no text.** If الدرر has no شرح or tafsir for the item, the API returns `reason: "no_source"` and the
   site says so. Nothing is generated from the model's general knowledge.

The retrieval of the *ruling* is not generative at all. It is search over the corpus, and the ruling is read verbatim
from the record.

## 11. AI components and how they are controlled

There are **no autonomous agents**. The pipeline is deterministic code that calls a model for a few narrow, bounded tasks.
Each call has a fixed prompt, returns JSON, is validated by code, and has a non-AI fallback or simply turns off.
**No model ever produces or changes a ruling.**

| Component | When it runs | Input → output | Guard | Without a model |
|---|---|---|---|---|
| **Transcriber** (vision) | Image input | Image → the text as written | Validated as an image before upload; whole transcription shown for user review; Tesseract fallback | Tesseract + OpenCV |
| **Extractor** | Long text, image or link | Text → cleaned text + quoted segments with type | Every segment must exist **literally** in the input; a rewritten "cleaned text" is discarded; honorific/reference spans are dropped | Rule-based spans |
| **Match checker** | English input, top three non-exact records | Input + records → same report or not, for each | Only a strong model (Groq `gpt-oss-120b`, or Anthropic) may **raise** a record, to partial at most; any model may **reject**; a Qur'an verse is never raised; "when unsure, false"; a match resting on meaning alone needs this confirmation. English is compared with English (the Arabic is sent only for a record without a translation, a third fewer tokens), and a verdict is reused for the same text | Wording-based matches stand; meaning-only matches are shown as the closest text |
| **Brief explainer** + **fact checker** | Every report, if enabled | Facts → 2–4 sentences in the chosen language | Code checks: no grade contradicting the record, no verdict when abstaining, no number absent from the facts. A second model pass flags claims the facts do not support (meaning, virtues, invented references). One rewrite with the problems listed, then a fixed template built only from the facts | Not shown |
| **Grounded explainer** | Extended explanation, on request | Facts + retrieved شرح/tafsir → summary | Source text is the only input; source link shown; no source → no text; language checked by script | Not shown |
| **Assistant classifier** | Assistant message the rules cannot place | Message → verify, report, tool or other | Only classifies; the action is code. A "verify" pointer must be text found literally in the message | Out-of-scope reply |
| **Assistant answerer** | Assistant question about the tool or the open report | Curated sections or report facts → 2–4 sentences | No numbers outside the sources; no contradicting grade; otherwise the curated text or the report's own wording | Curated text or report wording |
| **Voice** (Groq Orpheus, or self-hosted Piper) | Spoken replies and the voice call | Sentence → speech | Speaks only text already shown on screen; a style instruction is not read aloud | Device voice |
| **Speech transcriber** (Whisper) | Voice input in the assistant | Audio → transcript, Arabic or English | Refused on silence, low confidence, repetition, other languages; transcript confirmed by the user before verifying | Typing only |

**Provider chain** (`app/llm.py`): one OpenAI-compatible client. The default order is Gemini (`gemini-flash-lite-latest`),
then Groq (`openai/gpt-oss-120b`), then OpenRouter (`google/gemma-4-26b-a4b-it:free`), and optionally Anthropic. With a
Gemini key, `gemini-3.1-flash-lite` follows the first Gemini model: it has its own free quota and reads images, so
screenshots are still read by a model when the first quota is used up (Tesseract was the next reader before, and it
garbles vocalised Arabic). With a Groq key, Groq's smaller `openai/gpt-oss-20b` is added as the last fallback: it has its own free quota. It is not a
strong judge, so it can never raise a match. It never writes an Arabic or English brief either: in a test it called
al-Bukhari «الراوي» (narrator) instead of the compiler. There, the fixed wording built from the facts is used. Rules:

- A provider that rate-limits or fails (408, 409, 425, 429, 5xx) cools down for 45 seconds, and the next one is tried.
- Each call has a 20-second total budget.
- The match checker prefers Groq.
- Reasoning models get `reasoning_effort: low`.
- Answers in the wrong language are retried once, then dropped.

**Free quotas and what they allow** (limits read from the providers' own responses on 4 October 2026; they change):

| Service | Free limit | Used by | Roughly allows per day |
|---|---|---|---|
| Gemini `flash-lite` | 500 requests a day | Brief explanations, assistant answers, OCR reading | 500 model answers |
| Gemini `3.1-flash-lite` (backup) | Its own daily quota | The same tasks, when the first Gemini quota is used up; reads images | a second pool of answers |
| Groq `gpt-oss-120b` | 1,000 requests and 200,000 tokens a day, 8,000 tokens a minute | Match checker (preferred), fallback for the rest | ~250 match checks (600 to 1,500 tokens each) |
| Groq `gpt-oss-20b` | 1,000 requests a day, 8,000 tokens a minute, its own daily tokens | Last fallback | a few hundred answers |
| Groq Whisper `large-v3` | 2,000 requests a day | Assistant voice input | 2,000 spoken turns |
| OpenRouter free models | A small daily cap | Fallback | a few dozen answers |
| Piper (self-hosted) | None | The assistant's voice | Unlimited (server CPU) |

What each action costs:

- **No model at all:** matching and verdicts, Arabic verification with explanations off, assistant greetings and small
  talk, the spoken voice.
- **One model call:** a brief explanation (plus a fact check), a question to the assistant about the tool or the
  open report, an English text whose match is not exact (match check).
- **One Whisper call:** each spoken assistant turn.

When a quota runs out, the next provider answers. When all are used up, verification still works (wording-based
matches stand), the assistant answers from its curated text, and explanations are hidden. Per-visitor limits in the
API keep one person from using the shared quota: 30 assistant messages, 40 voice turns, 120 spoken sentences and 10
review PDFs per 10 minutes. Benchmarks should run with separate keys, because they use the same daily quotas as the
live site.

## 11a. The assistant

A floating button at the bottom right of every page, «اسأل سند» ("Ask Sanad"), opens the assistant. Its name is
**Sanad (سند)**, both "support" and the hadith term for a chain of narrators. On the first open of a session it greets
aloud: «السلام عليكم، أنا سند… كيف حالك؟». It answers small talk such as «كيف حالك؟», «الحمد لله بخير», «اسمي أحمد»
and «من أنت؟» with fixed replies. Small talk is never sent to verification. Its scope is deliberately limited to three
things: verify a hadith typed or spoken, explain the report open on the page, and answer questions about the tool.
Anything else, including general religious questions, gets a fixed reply. Personal fatwa and legal-ruling questions
are referred to scholars, and requests to write a hadith are refused. The code is `backend/app/assistant.py`.

**Routing** is deterministic first. Attribution phrases, quote marks, or a verify request that names a hadith go to
verification. A legal question such as «ما حكم …» or «هل يجوز …» goes to referral. Questions about the open report go to
the report responder, and questions with tool vocabulary go to the knowledge base. A model is asked only to *classify*
an ambiguous message. If it says "verify", the text it points to must appear literally in the message.

**Responders:**

| Kind | Source of the answer | Guard |
|---|---|---|
| Verify | The verification pipeline's report | The reply is built by code from the report: state, verbatim ruling, source, number. No model writes it. The report is stored in the browser and linked as the full report |
| Report question | The open report's facts and the state definitions | Model answer checked by code: no contradicting grade, no number absent from the facts. Otherwise the report's own wording is returned |
| Tool question | `backend/app/assistant_kb.md`, 13 curated sections in Arabic and English | Hybrid retrieval: best of three embeddings per section, plus a boost for section keywords. Below a minimum score the assistant says it only answers about verification and the tool. A model answer may not add numbers absent from the sections; otherwise the curated paragraph is returned as is |

**Voice** (`backend/app/stt.py`, `POST /api/stt`): the browser records up to 60 seconds and Whisper transcribes on
Groq. Rules applied, each with a clear message instead of a guess:

| Case | Rule | Code |
|---|---|---|
| Silence | In the browser: less than 0.5 s of audible sound while recording, so nothing is uploaded. On the server: every segment more likely silent than 0.6, a recording shorter than 1 s, or a phrase Whisper is known to invent on silence | `stt_no_speech` |
| Guessing | Mean log-probability below −1.0, or repetitive output with a compression ratio above 2.4 | `stt_unclear` |
| Language | Anything other than Arabic or English | `stt_language` |
| Length | Over 60 s or 5 MB | `stt_too_long` |
| Service | No key, rate limit or outage | `stt_unavailable` |

The transcript is always shown with "Is this what you said?" and is verified only after the user confirms or edits it.
No hint prompt is sent, because in tests Whisper echoed a prompt back on silence. Audio is not stored.

**Spoken conversation** («تحدث مع سند», `frontend/components/assistant/VoiceCall.tsx`, `frontend/lib/voice.ts`):

1. سند says «تفضل، أنا أستمع إليك» and listens. The recording stops by itself 1.3 s after you stop speaking, or ends
   the turn if nobody spoke for 9 s.
2. Whisper transcribes the recording. `POST /api/assistant` with `route_only` says what kind of message it is.
3. If it is a hadith to verify, سند reads it back: «سمعتك تقول: … هل أتحقق منه؟». It listens for «نعم» or «لا»; the
   on-screen buttons also work. A «لا», silence or anything unclear means nothing is verified, and it asks you to repeat.
4. The verdict is spoken sentence by sentence, then it listens again. After two silent turns it ends the call politely.

The microphone is closed while سند speaks, so it never hears itself. Ending the call or closing the panel stops
everything.

**Voice** (`backend/app/tts.py`, `POST /api/tts`): one sentence per request, so playback starts while the next sentence
is generated. Repeated phrases are cached in memory. Providers in order:

1. Groq Orpheus Saudi Arabic or English, once voices are configured and the model terms accepted in the Groq console.
2. **Piper, self-hosted on the server.** It uses the Arabic voice `ar_JO-kareem-medium`, the English voice
   `en_US-ryan-medium` and automatic Arabic diacritisation. It takes about 0.2 to 0.9 s per sentence on the server's CPU,
   with no quota and no key. This is the default voice.
3. Gemini TTS, off by default. Its free tier allows 10 requests a day, so a conversation exhausted it, and the voice
   switched to the device's mid-reply.
4. Otherwise the device's own voice.

Before speaking, numbers are read as Arabic words: «برقم 1907a» becomes «برقم ألف وتسعمئة وسبعة». API keys travel in
headers, never in URLs, so they cannot appear in access logs.

Spoken replies are on by default, with a mute button remembered on the device.

**Spelling correction of Arabic voice transcripts** (`backend/app/voice_fix.py`): Whisper makes spelling slips on
classical Arabic, such as «لو لا» for «لولا», «بن» for «ابن», «يصل» for «يصلي», «شفاع» for «شفاعه» and «مرئ» for
«امرئ». When the transcript matches a source text at 80 or more, each mismatched stretch is compared with the
source's words in a spelling-blind form: spaces, hamza, a leading alef or «ال», and weak endings ignored. The source's
spelling is used only when the two forms are then identical. Rules:

- A different word is never changed: «بالنية», a real narration, stays «بالنية».
- Words the speaker added are kept, and missing words are never inserted.
- The raw transcript is shown under the corrected one as "as heard".

On the voice benchmark this lowered the Arabic word error rate from 10% to 0% median and 5% mean, with 13 of 20
transcripts perfect.

**Misheard attributions:** speech-to-text sometimes garbles the opening, for example «قال رسول الله» heard as
«ورحمة الله». Anything before «صلى الله عليه وسلم» within the first six words is therefore treated as the attribution
and removed before matching. Without this, «إنما الأعمال بالنيات» fell one point short of "partial".

**Limits:** 30 assistant messages, 40 recordings and 120 spoken sentences per user per 10 minutes, kept in memory.

**Voice benchmark** (`backend/eval/voice/`, synthetic voices from macOS, run against real Whisper and the live API):

| Set | Right hadith | Median word error rate |
|---|---|---|
| Arabic: 20 authentic hadiths read aloud | 20 of 20 | 10% as heard, 0% after spelling correction (mean 5%, 13/20 perfect) |
| English: 10 published translations read aloud | 9 of 10 | 5% |
| Silence, French, noise | 3 of 3 refused with the right message | — |

The one English miss was a record whose text is only a stub. Real recordings can be added under `qa/voice/real/` with
a labels file and run the same way.

## 12. API reference

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Status, database connection, corpus counts, embedder, LLM chain, OCR availability |
| POST | `/api/verify` | Verify `{text \| url, lang, via, explain}` and return the full report |
| POST | `/api/verify/stream` | The same, as Server-Sent Events: `progress` steps, then `result` |
| POST | `/api/ocr` | Image (multipart) → transcribed text for review |
| POST | `/api/explain` | Brief or extended explanation of an existing report, in any listed language |
| GET | `/api/explain/languages` | The 25 explanation languages |
| GET | `/api/dorar` | Rulings from الدرر for a matched hadith: cards, best entry, search URL |
| GET | `/api/sources` | The approved sources list |
| POST | `/api/assistant` | The assistant: `{message, lang, report?}` → reply, kind, and the full report for verifications |
| POST | `/api/tts` | One sentence → natural speech (WAV); 503 lets the browser use the device voice |
| POST | `/api/stt` | Audio (multipart) → transcript, language, duration, confidence; or a `stt_*` error with a message |
| POST | `/api/review` | Ask for a human review (forwarded to a webhook when configured; nothing stored) |
| POST | `/api/review/pdf` | `{report_id, text, lang, tz}` → the result page printed as a PDF (the same document as the export button) behind a private link, kept 14 days. Only reports this server produced are printed: the one just shown (kept in memory), otherwise the text is verified again. 10 per 10 minutes per visitor |
| GET | `/api/review/pdf/{token}` | The review PDF (`noindex`, not cached); 404 once expired |

Errors use `{detail: {code, message}}`, for example `too_long` (413), `image_too_large` (413), `ocr_failed` (415/422),
`url_unreachable` (422), `wrong_language` (422: the text is not in the interface language; the message says which
interface to use).

## 13. Frontend

Next.js App Router, statically exported (`frontend/out`), with four screens:

- **Verify** (`/`): text, image or link input, with example chips.
- **Result** (`/result/?id=`): status banner, then these cards:
  - extracted text;
  - segments;
  - word diff, translation accuracy and glossary notes;
  - grade and source, الدرر rulings, narrations;
  - AI explanation, closest matches and actions.
- **Sources and methodology** (`/sources/`): every approved source and its role.
- **Recent checks** (`/recent/`): this browser session only.

Details:

- **Languages:** Arabic RTL by default, English LTR. The choice is kept in `localStorage`.
- **PDF export:** the browser's print-to-PDF with a dedicated print layout (A4). The browser draws Arabic correctly and
  keeps the text selectable, which JavaScript PDF libraries often fail at. A disclaimer footer is added.
- **Human review:** the review button opens a dialog for name and email. The server makes the PDF by printing the
  site's own result page with a headless Chromium, so it is the same document as the export button. The browser then
  sends the request to the team's inbox through a Web3Forms contact form, with the PDF link. The name and email go to
  the form only, never to the API. The free Web3Forms plan accepts browser submissions only and has no attachments,
  hence the link. The form key is public by design: it can only send to the form's owner.
- **Share image:** a 1080 × 1350 PNG drawn on a canvas with the page's fonts. It shows the state, the input, the recorded
  ruling and its source, the disclaimer and the site address. Phones use the system share sheet; computers download it.
- **Assistant widget:** a floating button at the bottom right opens the chat panel on every page. It supports text,
  voice with a confirmation step, reading replies aloud with the device's voice, and Escape to close. The conversation
  is kept in `sessionStorage` only.
- **Accessibility:** skip link, focus rings, live regions for progress and results, meter roles, colour contrast that
  passes WCAG AA (audited with axe-core).
- **Storage:** reports and history in `sessionStorage`, preferences in `localStorage`. Nothing about the user's texts
  leaves the browser except the verification request itself.

## 14. Quality: tests and benchmarks

**Tests:**

| Suite | Count | Command |
|---|---|---|
| Backend unit tests (offline, real saved fixtures) | 195 | `cd backend && .venv/bin/pytest -q` |
| Integration tests against the running stack | 37 | `TAHQAQ_STACK=1 .venv/bin/pytest tests/integration -q` |
| Browser tests (Playwright, Chrome), Arabic and English | 52 | `cd frontend && npx playwright test e2e/matrix.spec.ts` |
| Accessibility audit (axe-core, WCAG 2.1 A/AA), every screen in both languages, and the review dialog | 12 | `npx playwright test e2e/a11y.spec.ts` |
| Phone-size tests (Pixel 7, iPhone 13 size), touch flow, no sideways scroll | 4 | `npx playwright test e2e/mobile.spec.ts` |
| Assistant: verification in chat, scope, report questions, voice confirm/error/silence, spoken call with yes and no, spoken greeting, keyboard, accessibility | 15 | `npx playwright test e2e/assistant.spec.ts` |

**Benchmarks** (`backend/eval/`, run against a live API):

| Set | What it is | Result |
|---|---|---|
| Labelled corpus set (`benchmark.jsonl`, 98 inputs, fixed seed) | Exact and variant quotes of Sahihayn hadiths, fabricated/weak seeds, exact and misquoted verses, invented texts, fatwa questions | 98% strict, **100% same hadith**, 0 attributions to another hadith, 6/6 invented texts abstain, median latency ~0.3 s |
| Circulated texts (`circulated.jsonl`, 50 sayings, 46 scored) | Sayings that circulate on social media; labels decided from الدرر rulings, quoted per item | Authentic 21/21 confirmed; weak/fabricated/not hadith 22/25 flagged or abstained, 3 closest text only; **0 dangerous errors** |
| Voice (`eval/voice/`, 33 recordings) | Arabic hadiths and English translations read by synthetic voices, plus silence, French and noise | Arabic 20/20 right hadith, English 9/10; Arabic word error rate 10% as heard, 0% median after spelling correction; English 5%; 3/3 refusals correct; no attribution to another hadith |
| English pastes (`run_english_paste.py`, 40 records) | The full published English of Bukhari and Muslim records as pasted from translation sites, narrator line and story included | **40/40** right hadith (34/40 before the like-for-like key and full-text comparison were added) |
| Language check (`detect_script_language`, every record, plus 111 texts in other languages) | Arabic texts (the saying and the full text with its chain, also retyped with Persian ya and kaf), the published English translations (full and the quoted words), and texts in French, Indonesian, Turkish and Urdu | Arabic **80,914/80,914** and English **80,802/80,802** recognised, **0** refused by mistake; 109 of the 111 other-language texts caught (the other 2 are checked as English and find no match) |

"Same hadith" means the returned record is the labelled one, or the labelled record appears among the returned
record's narrations.

## 15. Security and privacy

- No user input is stored on the server, except a review PDF that the person asks for with their name and email
  (deleted after 14 days, behind an unguessable link). No accounts, no analytics.
- The database is not exposed, and the API is reached only through Caddy over HTTPS.
- CORS allows only the site's origin and localhost.
- Input limits: 2,000 characters, images up to 10 MB in PNG or JPG only, and the bytes are validated as an image before
  anything is sent to a model.
- Secrets live in the server's `.env` and in GitHub Actions secrets, never in the repository.
- Model calls carry only the text needed for the step.
- Rulings are quoted, never generated, and the UI says so on every result and in every PDF and share image.

## 16. Configuration reference

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql://tahqaq:tahqaq@localhost:5432/tahqaq` | Database |
| `EMBEDDER` / `EMBED_MODEL` | `local` / MiniLM-L12 | Embedding backend and model (`openai` and `hash` exist for small hosts and tests) |
| `LLM_PROVIDER` / `LLM_FALLBACKS` | `none` / empty | Provider chain, for example `gemini` and `groq,openrouter` |
| `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY` | empty | Provider keys |
| `LLM_MODEL`, `LLM_TIMEOUT` | empty, 15 s | Override the primary model; per-request timeout |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed browser origins |
| `REVIEW_WEBHOOK_URL` | empty | Where human-review requests are forwarded |
| `API_HOST` (prod) | — | Hostname Caddy serves and certifies |
| `POSTGRES_PASSWORD` (prod) | — | Database password |
| `NEXT_PUBLIC_API_URL` (frontend build) | `http://localhost:8000` | API address baked into the static site |

Thresholds (`threshold_verified` 90, `threshold_partial` 75, `threshold_uncertain` 50) are in `app/config.py`.

## 17. Known limits

- The searchable corpus is the Six Books, the Qur'an and a small curated list. A saying found only in other collections
  is not matched. The tool abstains, and the الدرر link lets the user search further.
- Only Arabic and English texts are checked; another language is refused, not machine-translated.
- Loosely paraphrased English often abstains. This is by design: precision before recall.
- The curated list of circulated sayings and the parallel-narration review were made by the developer from الدرر
  rulings, not by a hadith specialist. A specialist review is the next step before a public launch.
- Instagram, Facebook, YouTube and TikTok links cannot be read. Paste the text or a screenshot instead.
- The API address is tied to the VM's public IP through sslip.io. A reserved IP, or a domain with a Cloudflare Tunnel,
  removes that dependency.
- Voice is accepted in Arabic and English only, and the voice benchmark uses synthetic voices. Real recordings in noisy
  places will do worse; the confidence rules then refuse rather than guess.
- Free model tiers have daily quotas (see [Free quotas](#11-ai-components-and-how-they-are-controlled)). The provider
  chain and the non-AI fallbacks keep verification working when they run out.

## 18. Repository layout

```
backend/
  app/          FastAPI app: pipeline, matcher, store, normalize, quotes, dorar, llm, ocr, fetch_url, schemas,
                assistant (+ assistant_kb.md), stt, ratelimit
  ingest/       idempotent ingestion steps and seeds
  eval/         benchmark sets, generators and runners (corpus, circulated, English pastes, voice)
  tests/        unit tests and integration tests (TAHQAQ_STACK=1)
frontend/
  app/          pages: verify, result, sources, recent
  components/   home and result cards, header, footer, banner
  lib/          API client, i18n, storage, session, share image, tokens
  e2e/          Playwright: matrix, accessibility, phones
  messages/     ar.json, en.json
deploy/         Caddyfile, backup script
design/         the exported UI design (source of truth for layout, colours and copy)
docker-compose.yml        development stack (db, api, web, ingest, fixtures)
docker-compose.prod.yml   production stack (db, api, caddy)
.github/workflows/        ci, deploy, uptime
```
