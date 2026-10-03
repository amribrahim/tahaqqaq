from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

State = Literal["verified", "partial", "uncertain", "abstain", "referral", "unreliable"]


class VerifyRequest(BaseModel):
    text: str = Field(default="", max_length=4000)
    url: str = ""
    lang: Literal["ar", "en"] = "ar"  # UI language for the generated explanation
    explain: bool = True  # false skips the optional AI steps (explanation, segment extraction); verdict unaffected
    via: Literal["text", "image", "url"] = "text"  # "image": the text came from the OCR step (AI extraction applies)


class GradeOut(BaseModel):
    grader_ar: str
    grader_en: str
    grade_ar: str
    grade_en: str
    source_ar: str
    source_en: str
    number: str = ""
    url: str = ""


class SourceOut(BaseModel):
    kind: str
    collection: str
    book_ar: str
    book_en: str
    number: str
    chapter_ar: str
    chapter_en: str
    type_ar: str
    type_en: str
    text_ar: str
    matn_ar: str
    text_en: str
    text_en_quote: str = ""  # the Prophet's words only (narrator preamble stripped)
    source_url: str
    alt_url: str
    note_ar: str = ""
    note_en: str = ""


class NarrationOut(BaseModel):
    """The same text recorded in another book or under another number."""
    collection: str
    book_ar: str
    book_en: str
    number: str
    grade_ar: str = ""
    grade_en: str = ""
    grader_ar: str = ""
    grader_en: str = ""
    similarity: int
    source_url: str = ""


class CandidateOut(BaseModel):
    rank: int
    collection: str = ""
    text_ar: str
    text_en: str
    book_ar: str
    book_en: str
    number: str
    kind: str
    confidence: int
    lexical: float
    semantic: float
    source_url: str
    accepted: bool


class TranslationOut(BaseModel):
    original_ar: str
    user_tokens: list[dict[str, Any]]
    approved_tokens: list[dict[str, Any]]
    approved_text: str
    needs_fix: bool
    issues: list[dict[str, Any]]


class SegmentOut(BaseModel):
    """A quoted segment found in a long input / page / image, with its own best match."""
    text: str
    type: str = "other"            # hadith | quran | saying | other (the extractor's guess, never a ruling)
    origin: str = "rules"          # ai | rules
    confidence: int = 0
    state: str = "abstain"
    book_ar: str = ""
    book_en: str = ""
    number: str = ""
    kind: str = ""
    source_url: str = ""


class VerifyResponse(BaseModel):
    id: str
    state: State
    confidence: int
    threshold: int = 75
    match_level: str = ""  # for "unreliable": the underlying match level (verified | partial)
    reason_ar: str
    reason_en: str
    input_text: str
    input_lang: Literal["ar", "en"]
    via: Literal["text", "image", "url"] = "text"
    extracted_text: str = ""  # OCR / URL extraction result, when applicable
    source: SourceOut | None = None
    grade: GradeOut | None = None
    grades: list[GradeOut] = []
    closest_only: bool = False  # uncertain: grading applies to the closest text, not the input
    diff_input: list[dict[str, Any]] = []
    diff_source: list[dict[str, Any]] = []
    translation: TranslationOut | None = None
    glossary_terms: list[dict[str, Any]] = []
    quran_note: dict[str, str] | None = None  # {"ar":..., "en":...} when an ayah was quoted as hadith
    candidates: list[CandidateOut] = []
    narrations: list[NarrationOut] = []
    # English / machine-translated input: a model compared the top records with the input (same report or not)
    match_check: dict | None = None  # {"model", "outcome": "confirmed" | "rejected" | "kept", "checked"}
    segments: list[SegmentOut] = []     # AI/rule-extracted quotations with their matches (long text, link, image)
    cleaned_text: str = ""              # AI-corrected OCR/page text (certain fixes only), when it differs
    machine_translation: dict[str, str] | None = None  # {"language","english","model"}: non-Arabic/English input, for matching only
    extraction_model: str | None = None
    ai_explanation: str | None = None  # labelled "شرح مولَّد بالذكاء الاصطناعي" in the UI
    ai_model: str | None = None
    created_at: str
    timings_ms: dict[str, int] = {}


class ReviewRequest(BaseModel):
    report_id: str
    text: str = Field(max_length=4000)
    state: str = ""
    note: str = Field(default="", max_length=1000)
    contact: str = Field(default="", max_length=200)


class HealthOut(BaseModel):
    status: str
    db: bool
    counts: dict[str, int]
    embedder: str
    llm: bool
    llm_provider: str = "none"
    llm_chain: list[str] = []
    ocr: bool
    version: str


class ExplainRequest(BaseModel):
    """Re-generate the AI explanation of an existing report in another language or mode (facts unchanged)."""
    lang: str = Field(default="ar", max_length=40)
    mode: Literal["brief", "extended"] = "brief"
    collection: str = ""   # matched record, used to retrieve the شرح / tafsir for the extended mode
    number: str = ""
    state: str
    confidence: int = 0
    input_text: str = Field(default="", max_length=4000)
    matched_text: str = Field(default="", max_length=4000)
    ruling: dict[str, Any] | None = None
    source: dict[str, Any] | None = None
    quran_note: dict[str, str] | None = None
    translation_issues: list[str] = []


class ExplainOut(BaseModel):
    explanation: str | None
    model: str | None
    lang: str
    mode: str = "brief"
    grounding: dict[str, str] | None = None  # {"source_ar","source_en","url"}: where the extended text comes from
    reason: str = ""                          # e.g. "no_source" when the reference has no شرح/tafsir for this text
