"""The assistant behind the chat widget, in a deliberately limited scope:

  verify   a hadith the user typed or said → the verification pipeline; the reply is built from the report only
  report   a question about the report open on the page → answered only from that report's facts
  tool     a question about Tahaqqaq (sources, method, states, privacy…) → answered only from assistant_kb.md
  fatwa / generate / greeting / out_of_scope → fixed replies

Routing is deterministic first; a model may only classify an ambiguous message, never act on its own. No reply ever
carries a ruling that is not quoted from the verification report. Nothing is stored server-side."""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import classify, llm, pipeline, review_pdf
from .embeddings import get_embedder
from .normalize import detect_script_language, normalize_ar
from .quotes import quote_candidates

log = logging.getLogger(__name__)
KB_PATH = Path(__file__).with_name("assistant_kb.md")
KB_MIN_SCORE = 0.40      # below this cosine the knowledge base has nothing relevant to say

_INTERROGATIVE = re.compile(r"^\s*(?:ما|ماذا|لماذا|لم|كيف|هل|متى|أين|اين|من هو|كم|أي|اي|what|why|how|when|where|which|who|does|do|is|are|can)\b", re.I)
_VERIFY_HINT = re.compile(r"تحقق|تحققي|تأكد|صحة|صحيح|يصح|صح\b|ثابت|يثبت|حكم|درجة|verify|check|authentic|sahih|is this (?:a )?hadith", re.I)
# Scaffolding around the hadith itself: «هل هذا حديث صحيح:», "is this hadith authentic:", trailing «صحيح؟»
_PREFIXES = [   # most specific first; each is applied once, in order
    r"^\s*هل\s+(?:يصح|صح|ثبت|يثبت)\s+(?:هذا\s+)?(?:حديث|الحديث|أن|قول)?\s*[:：]?\s*",
    r"^\s*(?:من\s+فضلك\s+|لو\s+سمحت\s+)?(?:تحقق|تحققي|تأكد|تأكدي|افحص|ابحث)\s*(?:لي)?\s*(?:من|عن)?\s*(?:صحة)?\s*(?:هذا|هذه)?\s*(?:الحديث|حديث|النص|القول)?\s*[:：]?\s*",
    r"^\s*(?:هل|ما)\s+(?:(?:هذا|هذه)\s+)?(?:الحديث|حديث|النص|القول)\s*(?:صحيح|ثابت)?\s*[:：؟?]?\s*",
    r"^\s*(?:ما\s+)?(?:صحة|حكم|درجة)\s+(?:هذا\s+)?(?:الحديث|حديث)\s*[:：]?\s*",
    r"^\s*(?:please\s+)?(?:verify|check|authenticate)\s*(?:this|the)?\s*(?:hadith|text|saying)?\s*[:：]?\s*",
    r"^\s*is\s+(?:this|the|it)\s+(?:a\s+)?(?:hadith\s+)?(?:authentic|sahih|true|correct|real)?\s*[:：?]?\s*",
]
_SUFFIX = re.compile(r"\s*(?:هل\s+(?:هو|هذا)\s+)?(?:حديث\s+)?(?:صحيح|ثابت|صحيح\s+أم\s+لا|is (?:it|this) (?:authentic|sahih|true))?\s*[؟?]+\s*$", re.I)
_TOOL = re.compile(r"مصادر|مصدر|منهج|كيف تعمل|كيف يعمل|كيف أستخدم|كيف استخدم|طريقة|الدرر|الذكاء الاصطناعي|دقة|نسبة الثقة|الثقة|"
                   r"حد القبول|خصوصية|تحفظ|تخزن|لغات|اللغة|الصوت|صوت|PDF|بي دي اف|مشاركة|الروايات|حالات|الحالة|مؤيد جزئي|"
                   r"غير مؤكد|امتناع|يمتنع|الشرح|التفسير|الجمهرة|الكتب الستة|المساعد|من أنت|ماذا تفعل|"
                   r"sources?|methodolog|how does|how do|how to|accuracy|confidence|threshold|privacy|stor(?:e|age)|"
                   r"languages?|voice|pdf|share|narrations?|states?|partial|uncertain|abstain|dorar|\bai\b|artificial|"
                   r"model|who are you|what can you", re.I)
_FIQH = re.compile(r"^\s*(?:ما|وش|ايش|شو)\s+حكم\s+(?!هذا\s+الحديث|حديث|الحديث|هذا\s+القول|هذا\s+النص)|^\s*(?:هل\s+يجوز|يجوز\s+لي|is it (?:halal|haram|permissible|allowed))", re.I)
_REPORT_REF = re.compile(r"هذا|هذه|النتيجة|التقرير|الحكم|الحديث|النص|الروايات|المصدر|الثقة|this|result|report|ruling|grade|"
                         r"narration|source|confidence", re.I)
_HOW_ARE_YOU = re.compile(r"كيف حالك|كيف الحال|كيفك|شلونك|شخبارك|عامل ايه|how are you|how r u", re.I)
_FINE = re.compile(r"^\s*(?:و\s*)?(?:الحمد لله|الحمدلله|بخير|تمام|كويس|زين|طيب|ماشي الحال|i'?m fine|i am fine|fine|good|great|ok(?:ay)?)\b", re.I)
_WHO = re.compile(r"من أنت|من انت|ما اسمك|وش اسمك|شو اسمك|عرف بنفسك|who are you|what(?:'s| is) your name", re.I)
_NAME = re.compile(r"(?:اسمي|my name is)\s+([^\s،,.!؟?]{2,20})", re.I)
_AND_YOU = re.compile(r"و\s*(?:أنت|انت|إنت|انتي|أنتِ)|and you|you\?", re.I)
_GREETING = re.compile(r"^\s*(?:السلام عليكم|سلام عليكم|مرحبا|مرحبًا|أهلا|اهلا|هلا|صباح الخير|مساء الخير|hi|hello|hey|salam|assalamu)", re.I)
_THANKS = re.compile(r"^\s*(?:شكرا|شكرًا|جزاك الله|جزاكم الله|thanks|thank you|jazak)", re.I)

FIXED = {
    "wrong_language": ("في الواجهة العربية أتحقق من النصوص العربية. قل الحديث أو اكتبه بالعربية، أو بدّل الواجهة إلى English للتحقق من نص إنجليزي.",
                       "In the English interface I check English texts. Say or write the hadith in English, or switch the interface to العربية to check an Arabic text."),
    "greeting": ("وعليكم السلام ورحمة الله. أنا سند، مساعدك في التحقق من الأحاديث. كيف حالك؟ قل لي الحديث الذي تريد أن نتحقق منه.",
                 "Peace be upon you. I am Sanad, your assistant for verifying hadiths. How are you? Tell me the hadith you would like to check."),
    "how_are_you": ("بخير والحمد لله، شكرًا لسؤالك. كيف أستطيع مساعدتك؟ قل لي الحديث الذي تريد أن نتحقق منه.",
                    "I am well, thank you for asking. How can I help? Tell me the hadith you would like to check."),
    "fine": ("الحمد لله، يسعدني ذلك. تفضل، قل لي الحديث الذي تريد أن نتحقق منه.",
             "Glad to hear it. Go ahead, tell me the hadith you would like to check."),
    "fine_and_you": ("الحمد لله، وأنا بخير، شكرًا لسؤالك. تفضل، قل لي الحديث الذي تريد أن نتحقق منه.",
                     "Glad to hear it, and I am well too, thank you. Go ahead, tell me the hadith you would like to check."),
    "who": ("أنا سند، مساعد أداة تحقّق. أتحقق لك من الأحاديث من المصادر المعتمدة وأنقل حكم العلماء كما هو، ولا أُصدر حكمًا من عندي.",
            "I am Sanad, the Tahaqqaq assistant. I verify hadiths against approved sources and relay the scholars' rulings as recorded; I never issue a ruling of my own."),
    "thanks": ("وإياكم. أرسل أي حديث آخر للتحقق منه.", "You are welcome. Send any other hadith to verify."),
    "fatwa": ("هذا سؤال شخصي يحتاج إلى فتوى من أهل العلم، وأنا لا أُفتي. أستطيع التحقق من نص حديث تريد نشره.",
              "This is a personal question that needs a fatwa from qualified scholars, and I do not give fatwas. I can verify the text of a hadith you want to share."),
    "generate": ("لا أؤلف أحاديث ولا نصوصًا تُنسب إلى النبي ﷺ. أرسل نصًا متداولًا وأتحقق منه.",
                 "I do not compose hadiths or texts attributed to the Prophet ﷺ. Send a circulating text and I will verify it."),
    "out_of_scope": ("أنا مخصص للتحقق من الأحاديث فقط: ألصق نص حديث أو قله، أو اسألني عن التقرير المفتوح أو عن مصادر الأداة وطريقة عملها.",
                     "I am dedicated to verifying hadiths only: paste or say a hadith, or ask me about the open report or the tool's sources and method."),
    "unavailable": ("لا أستطيع الإجابة عن هذا السؤال الآن. التحقق من الأحاديث يعمل دائمًا: ألصق نص الحديث.",
                    "I cannot answer this question right now. Verifying a hadith always works: paste its text."),
}

STATE_LABEL = {
    "verified": ("مؤيَّد بمصدر", "Confirmed by a source"),
    "partial": ("مؤيَّد جزئيًا مع اختلاف في اللفظ", "Partially confirmed, with variant wording"),
    "uncertain": ("غير مؤكد", "Not confirmed"),
    "unreliable": ("وُجد النص وحكمه لا يصح", "Found, and its ruling is not authentic"),
    "abstain": ("لا مرجع، أمتنع عن الحكم", "No reference, I abstain"),
    "referral": ("إحالة إلى أهل العلم", "Referred to scholars"),
}


def _lang_of(message: str, ui_lang: str) -> str:
    s = detect_script_language(message)
    return s if s in ("ar", "en") else ("ar" if ui_lang == "ar" else "en")


def _fixed(kind: str, lang: str) -> dict:
    ar, en = FIXED[kind]
    return {"kind": kind, "reply": ar if lang == "ar" else en, "lang": lang}


# -- routing -----------------------------------------------------------------------------------------
def payload_of(message: str) -> str:
    """The hadith text inside a message: quoted text if any, else the message without the verify scaffolding."""
    t = message.strip()
    for p in _PREFIXES:
        t = re.sub(p, "", t, count=1, flags=re.I)
    t = _SUFFIX.sub("", t).strip(" :：«»\"“”")
    quoted = [s for s in quote_candidates(message) if len(s) < len(message) * 0.95]
    if quoted and re.search(r"[«\"“]", message):
        return quoted[0]
    return t


def route(message: str, has_report: bool) -> str:
    m = message.strip()
    words = m.split()
    if classify.is_generation_request(m):
        return "generate"
    attributed = classify.looks_like_attribution(m)
    if _FIQH.search(m) and not attributed:
        return "fatwa"          # «ما حكم صلاة الجماعة؟», «هل يجوز…» ask for a legal ruling, not about a text
    payload = payload_of(m)
    pwords = payload.split()
    if attributed or re.search(r"[«“]|\"[^\"]{8,}\"", m):
        return "verify"
    if re.search(r"حديث|hadith", m, re.I) and _VERIFY_HINT.search(m) and len(pwords) >= 3 and not _TOOL.search(payload):
        return "verify"         # «هل يصح حديث …» asks whether a hadith is authentic, not whether something is permissible
    if classify.is_personal_fatwa(m):
        return "fatwa"
    if len(words) <= 8 and _WHO.search(m):
        return "who"
    if len(words) <= 8 and _HOW_ARE_YOU.search(m):
        return "how_are_you"
    if len(words) <= 8 and _NAME.search(m) and not attributed:
        return "name"
    if len(words) <= 6 and _GREETING.search(m):
        return "greeting"
    if len(words) <= 6 and _FINE.search(m):
        return "fine_and_you" if _AND_YOU.search(m) else "fine"
    if len(words) <= 6 and _THANKS.search(m):
        return "thanks"
    if _VERIFY_HINT.search(m) and len(pwords) >= 3 and not _TOOL.search(payload):
        return "verify"
    is_question = bool(_INTERROGATIVE.search(m) or re.search(r"[؟?]\s*$", m))
    if has_report and is_question and _REPORT_REF.search(m):
        return "report"          # «لماذا النتيجة مؤيد جزئيًا؟» is about the open report, even with tool words in it
    if _TOOL.search(m) and is_question:
        return "tool"
    if has_report and is_question:
        return "report"
    arabic = detect_script_language(m) == "ar"
    if arabic and len(words) >= 3 and not is_question:
        return "verify"          # a pasted Arabic text without a question is almost always a quote to check
    if _TOOL.search(m):
        return "tool"
    return "ambiguous"


CLASSIFY_SYSTEM = """You route messages for a hadith-verification assistant. Decide what the user wants:
"verify" - the message contains a hadith or a saying attributed to the Prophet that should be checked;
"report" - a question about the verification report the user is looking at;
"tool" - a question about the tool itself (sources, method, accuracy, privacy, languages, features);
"other" - anything else (general religious questions, chat, other topics).
Return JSON: {"intent": "verify" | "report" | "tool" | "other", "text": "<the hadith text copied exactly from the message, only for verify>"}"""


def _classify_with_model(message: str, has_report: bool) -> tuple[str, str]:
    out = llm.get_client().complete(CLASSIFY_SYSTEM, f"Report open: {has_report}\nMessage: {message}", json_mode=True, max_tokens=300)
    if not out:
        return "other", ""
    try:
        d = json.loads(out[0])
    except ValueError:
        return "other", ""
    intent = d.get("intent") if d.get("intent") in ("verify", "report", "tool", "other") else "other"
    text = (d.get("text") or "").strip()
    if intent == "verify" and (not text or text not in message):
        text = payload_of(message)           # the model may only point at text that is literally in the message
    if intent == "report" and not has_report:
        intent = "tool"
    return intent, text


# -- responders ----------------------------------------------------------------------------------------
def _ruling_line(g: dict, lang: str) -> str:
    if lang == "ar":
        where = f"{g.get('source_ar', '')} برقم {g['number']}" if g.get("number") else g.get("source_ar", "")
        return f"الحكم: {g.get('grade_ar', '')}، {g.get('grader_ar', '')}، في {where}."
    where = f"{g.get('source_en') or g.get('source_ar', '')}, number {g['number']}" if g.get("number") else (g.get("source_en") or g.get("source_ar", ""))
    return f"Ruling: {g.get('grade_en') or g.get('grade_ar', '')}, {g.get('grader_en') or g.get('grader_ar', '')}, in {where}."


def compose_verify(r: dict, lang: str) -> str:
    """The verification reply, built only from the report (no model)."""
    ar = lang == "ar"
    state = r["state"]
    label = STATE_LABEL[state][0 if ar else 1]
    g, src = r.get("grade") or {}, r.get("source") or {}
    parts = [label + "."]
    if state == "referral":
        parts.append(FIXED["fatwa"][0 if ar else 1])
    elif state == "abstain":
        parts.append("لم أجد هذا النص في مصادرنا المعتمدة، لذلك لا أنسبه ولا أحكم عليه. يمكنك البحث عنه في الدرر السنية." if ar else
                     "I did not find this text in our approved sources, so I neither attribute nor grade it. You can search for it on Dorar.net.")
    elif src.get("kind") == "quran":
        note = (r.get("quran_note") or {}).get("ar" if ar else "en")
        parts.append(note or (f"هذا نص آية من القرآن الكريم: {src.get('chapter_ar', '')}." if ar else
                              f"This is a verse of the Qur'an: {src.get('chapter_en', '')} {src.get('number', '')}."))
    elif state == "uncertain":
        where = f"{src.get('book_ar', '')} برقم {src.get('number', '')}" if ar else f"{src.get('book_en', '')} {src.get('number', '')}"
        parts.append(f"لا يوجد نص بهذا اللفظ. أقرب نص في {where}، ولا يُنسب حكمه إلى ما أرسلته." if ar else
                     f"No text has this wording. The closest is {where}, and its ruling does not apply to your text.")
    elif g:
        parts.append(_ruling_line(g, lang))
        if state == "unreliable":
            parts.append("لا يُنشر على أنه حديث ثابت." if ar else "It should not be shared as an established hadith.")
        n = len(r.get("narrations") or [])
        if n:
            parts.append(f"وللنص نفسه {n} مواضع أخرى في كتب الحديث." if ar else f"The same text appears in {n} other places in the hadith books.")
    parts.append("التقرير الكامل يعرض النص والمصادر والتفاصيل." if ar else "The full report shows the text, the sources and the details.")
    return " ".join(p for p in parts if p)


def _verify(text: str, lang: str) -> dict:
    report = pipeline.run(text, lang_ui=lang, via="text", explain=False).model_dump()
    review_pdf.remember(report)
    return {"kind": "verify", "reply": compose_verify(report, lang), "lang": lang, "report": report}


@lru_cache(maxsize=1)
def _kb() -> list[tuple[str, str, np.ndarray]]:
    """Sections of assistant_kb.md: (title, body, vectors), vectors = [title+keywords, Arabic paragraph, English paragraph]."""
    sections, title, body, keywords = [], None, [], {}
    for line in KB_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            if title:
                sections.append((title, "\n".join(body).strip()))
            title, body = line[2:].strip(), []
        elif line.startswith("keywords:") and title:
            keywords[title] = line.split(":", 1)[1].strip()
        elif title:
            body.append(line)
    if title:
        sections.append((title, "\n".join(body).strip()))
    texts = []
    for t, b in sections:
        texts += [f"{t}. {keywords.get(t, '')}", _paragraph(b, "ar"), _paragraph(b, "en")]
    vecs = get_embedder().embed(texts)
    _KEYWORDS.clear()
    _KEYWORDS.update({t: [normalize_ar(k) for k in re.split(r"[،,/]", keywords.get(t, "")) if len(k.strip()) >= 3] for t, _ in sections})
    return [(t, b, vecs[3 * i : 3 * i + 3]) for i, (t, b) in enumerate(sections)]


_KEYWORDS: dict[str, list[str]] = {}
KEYWORD_BOOST = 0.30


def search_kb(question: str, k: int = 2) -> list[tuple[str, str, float]]:
    """Best sections for a question: the best of three embeddings per section, plus a boost when one of the section's
    keywords appears in the question."""
    kb = _kb()
    q = get_embedder().embed([question])[0]
    nq = normalize_ar(question)
    scored = []
    for t, b, vs in kb:
        score = float(max(np.dot(v, q) for v in vs))
        if any(kw and kw in nq for kw in _KEYWORDS.get(t, [])):
            score += KEYWORD_BOOST
        scored.append((t, b, score))
    scored.sort(key=lambda x: -x[2])
    return scored[:k]


def _paragraph(body: str, lang: str) -> str:
    """The Arabic or the English paragraph of a knowledge-base section."""
    paras = [p for p in body.split("\n") if p.strip()]
    for p in paras:
        if (detect_script_language(p) == "ar") == (lang == "ar"):
            return p.strip()
    return paras[0].strip() if paras else ""


TOOL_SYSTEM = """You answer questions about Tahaqqaq, a hadith-verification tool, using ONLY the sections provided.
Rules: 2-4 short sentences; no information that is not in the sections; never state or judge a ruling on any hadith;
no fatwas. If the sections do not answer the question, say you can only answer questions about verifying hadith and
this tool. Write in {language}. Return JSON: {{"answer": "<text>"}}"""

REPORT_SYSTEM = """You explain a hadith-verification report to the person reading it, using ONLY the report facts and the
definitions provided. Rules: 2-5 short sentences; never add, change or soften a ruling; never judge authenticity
yourself; quote rulings only as they appear in the facts; no fatwas; if the facts do not answer the question, say so.
Write in {language}. Return JSON: {{"answer": "<text>"}}"""


def _numbers_ok(text: str, allowed_source: str) -> bool:
    allowed = set(re.findall(r"\d+", allowed_source.translate(llm._DIGITS)))
    return all(n in allowed for n in re.findall(r"\d+", text.translate(llm._DIGITS)))


def _answer(system: str, user: str, lang: str, allowed: str) -> tuple[str, str] | None:
    language = "Arabic (fusha)" if lang == "ar" else "English"
    out = llm.get_client().complete(system.format(language=language), user, json_mode=True, max_tokens=500)
    if not out:
        return None
    try:
        text = (json.loads(out[0]).get("answer") or "").strip()
    except (ValueError, AttributeError):
        text = out[0].strip()
    if not text or not llm.script_matches(text, lang) or not _numbers_ok(text, allowed):
        return None
    return text, out[1]


def _tool(message: str, lang: str) -> dict:
    hits = [h for h in search_kb(message) if h[2] >= KB_MIN_SCORE]
    if not hits:
        return _fixed("out_of_scope", lang)
    sections = "\n\n".join(f"## {t}\n{b}" for t, b, _ in hits)
    sources = [t for t, _, _ in hits]
    got = _answer(TOOL_SYSTEM, f"Sections:\n{sections}\n\nQuestion: {message}", lang, sections) if llm.get_client().enabled else None
    if got:
        return {"kind": "tool", "reply": got[0], "lang": lang, "sources": sources, "model": got[1]}
    # no model (or its answer failed the checks): the curated paragraph itself, which is accurate by construction
    return {"kind": "tool", "reply": _paragraph(hits[0][1], lang), "lang": lang, "sources": sources[:1]}


def _report_facts(report: dict) -> dict:
    keys = ("state", "confidence", "input_text", "reason_ar", "reason_en", "closest_only", "match_check")
    facts = {k: report.get(k) for k in keys if report.get(k) is not None}
    if report.get("source"):
        s = report["source"]
        facts["source"] = {k: s.get(k) for k in ("kind", "book_ar", "book_en", "number", "chapter_ar", "chapter_en")}
    if report.get("grade"):
        facts["ruling"] = report["grade"]
    facts["other_rulings"] = (report.get("grades") or [])[1:4]
    facts["narrations"] = [{k: n.get(k) for k in ("book_ar", "book_en", "number", "grade_ar", "grade_en")} for n in (report.get("narrations") or [])[:5]]
    return facts


def _report(message: str, lang: str, report: dict) -> dict:
    facts = _report_facts(report)
    defs = "\n".join(b for t, b, _ in _kb() if t in ("Result states", "Confidence and acceptance threshold"))
    facts_json = json.dumps(facts, ensure_ascii=False)
    got = _answer(REPORT_SYSTEM, f"Definitions:\n{defs}\n\nReport facts: {facts_json}\n\nQuestion: {message}", lang,
                  facts_json + defs) if llm.get_client().enabled else None
    if got and not llm.check_brief(got[0], {"state": facts.get("state"), "ruling": facts.get("ruling"), "confidence": facts.get("confidence"),
                                             "source": facts.get("source"), "narrations": facts.get("narrations")}):
        return {"kind": "report", "reply": got[0], "lang": lang, "model": got[1]}
    # fallback: what the report already says, word for word
    return {"kind": "report", "reply": compose_verify(report, lang), "lang": lang}


def route_kind(message: str, has_report: bool) -> str:
    """The kind of a message without acting on it (the voice flow asks for a spoken confirmation before verifying)."""
    kind = route((message or "").strip(), has_report)
    if kind == "ambiguous":
        kind = _classify_with_model(message, has_report)[0] if llm.get_client().enabled else "other"
    return {"other": "out_of_scope"}.get(kind, kind)


def reply(message: str, ui_lang: str = "ar", report: dict | None = None) -> dict:
    message = (message or "").strip()
    lang = _lang_of(message, ui_lang)
    if not message:
        return _fixed("out_of_scope", lang)
    kind = route(message, report is not None)
    text = ""
    if kind == "ambiguous":
        kind, text = _classify_with_model(message, report is not None) if llm.get_client().enabled else ("other", "")
        kind = {"other": "out_of_scope"}.get(kind, kind)
    if kind == "verify":
        payload = text or payload_of(message)
        if len(payload.split()) < 2:
            return _fixed("out_of_scope", lang)
        if detect_script_language(payload) != ui_lang:   # Arabic in the Arabic interface, English in the English one
            return _fixed("wrong_language", ui_lang)
        return _verify(payload, ui_lang)
    if kind == "report" and report is not None:
        return _report(message, lang, report)
    if kind == "tool":
        return _tool(message, lang)
    if kind == "name":
        name = _NAME.search(message).group(1)
        text = (f"تشرفت بمعرفتك يا {name}. أنا سند. قل لي الحديث الذي تريد أن نتحقق منه." if lang == "ar"
                else f"Nice to meet you, {name}. I am Sanad. Tell me the hadith you would like to check.")
        return {"kind": "name", "reply": text, "lang": lang}
    if kind in FIXED:
        return _fixed(kind, lang)
    return _fixed("out_of_scope", lang)
