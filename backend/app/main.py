from __future__ import annotations

import json
import logging
import re
import shutil
import time
from collections.abc import Iterator

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from . import assistant, fetch_url, llm, ocr, pipeline, ratelimit, review_pdf, stt, tts, voice_fix
from .config import get_settings
from .embeddings import get_embedder
from .normalize import detect_language
from .schemas import (
    AssistantRequest,
    ExplainOut,
    ExplainRequest,
    HealthOut,
    ReviewPdfRequest,
    ReviewRequest,
    TTSRequest,
    VerifyRequest,
    VerifyResponse,
)
from .store import get_store

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("tahqaq")
VERSION = "0.1.0"

app = FastAPI(title="Tahaqqaq API", version=VERSION, docs_url="/docs")
settings = get_settings()
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_list, allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("startup")
def _warm() -> None:
    # Load the embedding model once so the first request is fast.
    try:
        get_embedder()
    except Exception as e:  # noqa: BLE001
        log.warning("embedder not ready: %s", e)


@app.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    db_ok, counts = False, {}
    try:
        counts = get_store().counts()
        db_ok = True
    except Exception as e:  # noqa: BLE001
        log.warning("health: db error %s", e)
    try:
        emb = get_embedder().name
    except Exception:  # noqa: BLE001
        emb = "unavailable"
    chain = llm.get_client().chain()
    return HealthOut(
        status="ok" if db_ok else "degraded", db=db_ok, counts=counts, embedder=emb,
        llm=bool(chain), llm_provider=(chain[0] if chain else "none"), llm_chain=chain,
        ocr=shutil.which("tesseract") is not None, version=VERSION,
    )


def _validate_text(text: str, limit: int | None = None) -> str:
    text = (text or "").strip()
    limit = limit or settings.max_input_chars
    if not text:
        raise HTTPException(400, {"code": "empty", "message": "no text to verify"})
    if len(text) > limit:
        raise HTTPException(413, {"code": "too_long", "message": f"text exceeds {limit} characters"})
    return text


def _resolve_input(req: VerifyRequest) -> tuple[str, str, str]:
    if req.url.strip():
        try:
            main, context = fetch_url.extract(req.url, max_chars=3000)
        except fetch_url.URLError as e:
            raise HTTPException(422, {"code": "url_unreachable", "message": str(e)}) from e
        return _validate_text(main, limit=3000), "url", context
    return _validate_text(req.text), ("image" if req.via == "image" else "text"), ""


@app.post("/api/verify", response_model=VerifyResponse)
def verify(req: VerifyRequest) -> VerifyResponse:
    text, via, extracted = _resolve_input(req)
    try:
        out = pipeline.run(text, req.lang, via, extracted, explain=req.explain)
    except Exception as e:
        log.exception("verify failed")
        raise HTTPException(503, {"code": "sources_unreachable", "message": str(e)}) from e
    review_pdf.remember(out.model_dump())
    return out


@app.post("/api/verify/stream")
def verify_stream(req: VerifyRequest) -> StreamingResponse:
    """Server-sent events: `progress` events (step 0..3) followed by one `result` event."""
    text, via, extracted = _resolve_input(req)

    def gen() -> Iterator[str]:
        try:
            for ev in pipeline.run_streaming(text, req.lang, via, extracted, explain=req.explain):
                if ev["event"] == "result":
                    review_pdf.remember(ev["data"])
                yield f"event: {ev['event']}\ndata: {json.dumps(ev['data'], ensure_ascii=False)}\n\n"
        except Exception as e:
            log.exception("verify stream failed")
            yield f"event: error\ndata: {json.dumps({'code': 'sources_unreachable', 'message': str(e)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/ocr")
async def ocr_endpoint(image: UploadFile = File(...), lang: str = Form("ar"), ai: str = Form("1")) -> dict:
    """ai="0" skips the vision-model transcription and uses Tesseract only (used by the test-suite)."""
    data = await image.read()
    if len(data) > settings.max_image_bytes:
        raise HTTPException(413, {"code": "image_too_large", "message": "image exceeds 10 MB"})
    if (image.content_type or "") not in ("image/png", "image/jpeg", "image/jpg", "image/webp"):
        raise HTTPException(415, {"code": "ocr_failed", "message": "PNG or JPG only"})
    try:
        text = ocr.extract_text(data, image.content_type or "image/png", use_ai=(ai != "0"))
    except ocr.OCRError as e:
        raise HTTPException(422, {"code": "ocr_failed", "message": str(e)}) from e
    full = text[: settings.max_input_chars]
    # The user reviews the WHOLE transcription; the pipeline then finds the saying inside it
    # (chain of narrators, attribution, commentary). Never pre-cut it here: OCR line breaks follow
    # the image's wrapping, so picking "the best line" cuts the hadith in half.
    return {"text": full, "full": full, "lang": detect_language(full)}


@app.post("/api/explain", response_model=ExplainOut)
def explain_endpoint(req: ExplainRequest) -> ExplainOut:
    """Write the explanation of an already verified report in the requested language.
    The facts come from the report; the model only words them (never grades). Nothing is stored."""
    facts = {
        "state": req.state, "confidence": req.confidence, "input": req.input_text, "matched_text": req.matched_text or None,
        "ruling": req.ruling, "source": req.source, "quran_note": req.quran_note,
        "translation_issues": req.translation_issues or None,
    }
    if req.mode == "extended" and (req.state in ("abstain", "referral", "uncertain") or not req.matched_text):
        # no matched source text to explain (or only a "closest" text that is not the user's)
        raise HTTPException(400, {"code": "no_extended", "message": "extended explanation needs a matched source text"})
    if not llm.get_client().enabled:
        return ExplainOut(explanation=None, model=None, lang=req.lang, mode=req.mode, reason="llm_disabled")
    if req.mode == "brief":
        out = llm.explain(facts, req.lang, "brief")
        return ExplainOut(explanation=out[0] if out else None, model=out[1] if out else None, lang=req.lang, mode="brief")
    # extended: RAG over the approved reference — شرح الحديث / موسوعة التفسير at الدرر السنية
    grounding = _extended_source(req)
    if not grounding:
        return ExplainOut(explanation=None, model=None, lang=req.lang, mode="extended", reason="no_source")
    out = llm.explain(facts, req.lang, "extended", source_text=grounding.pop("text"))
    return ExplainOut(explanation=out[0] if out else None, model=out[1] if out else None, lang=req.lang,
                      mode="extended", grounding=grounding)


def _extended_source(req: ExplainRequest) -> dict | None:
    from . import dorar

    rec = get_store().get_record(req.collection, req.number) if req.collection and req.number else None
    try:
        if rec and rec.kind == "quran":
            surah, ayah = (int(x) for x in rec.number.split(":"))
            t = dorar.get_dorar().tafseer_for(surah, ayah)
            if t and len(t.get("text", "")) > 200:
                return {"text": t["text"], "url": t["url"], "source_ar": f"موسوعة التفسير — الدرر السنية · {t['title']}",
                        "source_en": f"Tafsir Encyclopedia — Dorar.net · {t['title']}"}
            return None
        matn = rec.matn_ar if rec else req.matched_text
        sh = dorar.get_dorar().sharh_for(matn, rec.book_ar if rec else "", rec.number if rec else "")
        if sh and len(sh["text"]) > 150:
            return {"text": sh["text"], "url": sh["url"], "source_ar": "شرح الحديث — الموسوعة الحديثية، الدرر السنية",
                    "source_en": "Hadith explanation — Dorar.net Hadith Encyclopedia"}
    except Exception as e:  # noqa: BLE001 - the reference may be unreachable; never fail the request
        log.warning("extended source unavailable: %s", e)
    return None


@app.get("/api/dorar")
def dorar_rulings(collection: str, number: str) -> dict:
    """Every scholar's ruling on the matched hadith, from الدرر السنية (cached in source_cache).
    The query is the matched record's own wording; the user's input is never sent."""
    from . import dorar

    rec = get_store().get_record(collection, number)
    if not rec or rec.kind == "quran":
        return {"available": False, "reason": "not_a_hadith", "cards": []}
    try:
        info = dorar.get_dorar().rulings_for(rec.matn_ar, rec.book_ar, rec.number)
    except Exception as e:  # noqa: BLE001
        log.warning("dorar unavailable: %s", e)
        return {"available": False, "reason": "unreachable", "cards": [], "search_url": dorar.DorarClient.search_url(rec.matn_ar)}
    return {"available": bool(info["cards"]), **info}


@app.get("/api/explain/languages")
def explain_languages() -> dict:
    return {"languages": llm.LANGUAGES, "enabled": llm.get_client().enabled}


@app.post("/api/review")
def review(req: ReviewRequest) -> dict:
    """Human-review request. Nothing is stored server-side. If REVIEW_WEBHOOK_URL is configured the
    request is forwarded there (the user explicitly asked for a human to read their text)."""
    forwarded = False
    if settings.review_webhook_url:
        try:
            payload = {"text": f"[Tahaqqaq] human review requested\nreport: {req.report_id}\nstate: {req.state}\n"
                               f"contact: {req.contact or '-'}\nnote: {req.note or '-'}\n\n{req.text}"}
            httpx.post(settings.review_webhook_url, json=payload, timeout=10).raise_for_status()
            forwarded = True
        except httpx.HTTPError as e:
            log.warning("review webhook failed: %s", e)
    return {"accepted": True, "forwarded": forwarded, "sla_hours": 48, "ts": int(time.time())}


@app.post("/api/review/pdf")
def review_pdf_create(req: ReviewPdfRequest, request: Request) -> dict:
    """The report as a PDF for a human-review request, kept for RETAIN_DAYS behind an unguessable link. Only reports
    this server produced are rendered: the one just shown (kept in memory), otherwise the text is verified again."""
    ratelimit.check(request, "review-pdf", limit=10, window_s=600, lang=req.lang)
    report = review_pdf.recall(req.report_id)
    if report is None:
        text = _validate_text(req.text)
        try:
            report = pipeline.run(text, req.lang, "text", explain=False).model_dump()
        except Exception as e:
            log.exception("review pdf: verify failed")
            raise HTTPException(503, {"code": "sources_unreachable", "message": str(e)}) from e
    try:
        pdf = review_pdf.render_pdf(report, req.lang, req.name.strip(), req.email.strip())
        token = review_pdf.save(pdf, report["id"])
    except Exception as e:
        log.exception("review pdf failed")
        raise HTTPException(503, {"code": "pdf_unavailable", "message": str(e)}) from e
    return {"token": token, "path": f"/api/review/pdf/{token}", "retain_days": review_pdf.RETAIN_DAYS,
            "report_id": report["id"], "state": report["state"], "confidence": report["confidence"]}


@app.get("/api/review/pdf/{token}")
def review_pdf_get(token: str) -> Response:
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,64}", token):
        raise HTTPException(404, {"code": "not_found", "message": "no such report"})
    found = review_pdf.load(token)
    if not found:
        raise HTTPException(404, {"code": "not_found", "message": "this report link has expired or does not exist"})
    pdf, report_id = found
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="tahaqqaq-report-{report_id}.pdf"',
        "Cache-Control": "private, no-store", "X-Robots-Tag": "noindex"})


@app.post("/api/assistant")
def assistant_endpoint(req: AssistantRequest, request: Request) -> dict:
    """The chat assistant, limited to verifying hadiths, explaining the open report and answering questions about the
    tool. Verification replies come from the pipeline's report only. Nothing is stored server-side."""
    if req.route_only:
        ratelimit.check(request, "assistant-route", limit=60, window_s=600, lang=req.lang)
        return {"kind": assistant.route_kind(req.message, req.report is not None)}
    ratelimit.check(request, "assistant", limit=30, window_s=600, lang=req.lang)
    return assistant.reply(req.message, req.lang, req.report)


@app.post("/api/tts")
def tts_endpoint(req: TTSRequest, request: Request) -> Response:
    """One sentence of the assistant's reply as natural speech (WAV). 503 when no voice provider answers: the browser
    then reads the text with the device's own voice. Nothing is stored."""
    ratelimit.check(request, "tts", limit=120, window_s=600, lang=req.lang)
    try:
        audio, mime = tts.synthesize(req.text, "ar" if req.lang == "ar" else "en")
    except tts.TTSUnavailable as e:
        raise HTTPException(503, {"code": "tts_unavailable", "message": "voice unavailable"}) from e
    return Response(content=audio, media_type=mime, headers={"Cache-Control": "no-store"})


@app.post("/api/stt")
async def stt_endpoint(request: Request, audio: UploadFile = File(...), lang: str = Form("ar")) -> dict:
    """Speech to text for the assistant (Arabic and English only). An unclear recording returns an error, never a guess;
    the transcript is shown to the user before anything is verified. Audio is not stored."""
    ratelimit.check(request, "stt", limit=40, window_s=600, lang=lang)
    data = await audio.read()
    try:
        out = stt.transcribe(data, audio.filename or "audio.webm", audio.content_type or "")
    except stt.STTError as e:
        raise HTTPException(e.status, {"code": e.code, "message": e.message(lang)}) from e
    out["heard"], out["corrected"] = out["text"], False
    if out["lang"] == "ar":
        try:
            out["text"], out["corrected"] = voice_fix.snap(out["text"])
        except Exception as e:  # noqa: BLE001 - the correction is an aid; the transcript stands without it
            log.warning("voice correction failed: %s", e)
    return out


@app.get("/api/sources")
def sources() -> dict:
    counts = {}
    try:
        counts = get_store().counts()
    except Exception:  # noqa: BLE001
        pass
    return {"counts": counts, "thresholds": {"verified": settings.threshold_verified, "partial": settings.threshold_partial,
                                            "uncertain": settings.threshold_uncertain}}
