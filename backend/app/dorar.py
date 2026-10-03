"""Read-only client for the challenge's approved references at الدرر السنية:
  - الموسوعة الحديثية (dorar.net/hadith): every scholar's ruling on a hadith, and its شرح,
  - موسوعة التفسير (dorar.net/tafseer): tafsir of a verse.
Everything fetched is cached in the `source_cache` table, so it becomes part of the retrieval corpus.
Queries are always built from the MATCHED SOURCE RECORD's wording, never from the user's input."""
from __future__ import annotations

import html as htmllib
import logging
import re
from urllib.parse import quote

import httpx
from rapidfuzz import fuzz

from .normalize import normalize_ar, strip_tashkeel

log = logging.getLogger(__name__)

BASE = "https://dorar.net"
_UA = {"User-Agent": "Mozilla/5.0 (compatible; Tahaqqaq/0.1; +https://github.com/amribrahim/tahaqqaq)"}
_TIMEOUT = 15.0

# book names as dorar writes them in «المصدر» (record.book_ar -> dorar source)
_BOOK_ALIASES = {
    "صحيح البخاري": ["صحيح البخاري"], "صحيح مسلم": ["صحيح مسلم"],
    "سنن أبي داود": ["سنن أبي داود", "صحيح أبي داود", "ضعيف أبي داود"],
    "جامع الترمذي": ["سنن الترمذي", "صحيح الترمذي", "ضعيف الترمذي"],
    "سنن النسائي": ["سنن النسائي", "صحيح النسائي", "ضعيف النسائي"],
    "سنن ابن ماجه": ["سنن ابن ماجه", "صحيح ابن ماجه", "ضعيف ابن ماجه"],
}


# ---------------------------------------------------------------------------------------------
def _text(fragment: str) -> str:
    t = re.sub(r"(?s)<script.*?</script>|<style.*?</style>", " ", fragment)
    t = htmllib.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t).strip()


def _field(text: str, label: str, stops: list[str]) -> str:
    # «المحدث» must not match inside «خلاصة حكم المحدث»
    guard = r"(?<!حكم )" if label == "المحدث" else ""
    stop_re = "|".join(r"(?<!حكم )المحدث" if s_ == "المحدث" else re.escape(s_) for s_ in stops if s_ != label)
    m = re.search(guard + re.escape(label) + r"\s*:\s*(.*?)\s*(?=" + stop_re + r"|$)", text)
    return m.group(1).strip(" |") if m else ""


_LABELS = ["خلاصة حكم المحدث", "الراوي", "المحدث", "المصدر", "الصفحة أو الرقم", "التخريج", "التصنيف الموضوعي", "شرح الحديث", "|"]


def parse_cards(page: str) -> list[dict]:
    """Result cards of a dorar hadith search page."""
    cards = []
    for chunk in page.split('<div class="border-bottom py-4')[1:]:
        h5 = re.search(r"(?s)<h5[^>]*>(.*?)</h5>", chunk)
        text = re.sub(r"^\d+\s*-\s*", "", _text(h5.group(1))) if h5 else ""
        body = _text(chunk)
        stops = [x for x in _LABELS]
        card = {
            "text": text,
            "grade": _field(body, "خلاصة حكم المحدث", stops),
            "narrator": _field(body, "الراوي", stops),
            "scholar": _field(body, "المحدث", stops),
            "book": _field(body, "المصدر", stops),
            "number": _field(body, "الصفحة أو الرقم", stops),
            "takhrij": _field(body, "التخريج", stops),
            "xplain": (re.search(r'xplain="(\d+)"', chunk) or [None, None])[1],
        }
        if card["text"] and card["grade"]:
            cards.append(card)
    return _dedupe(cards)


def _dedupe(cards: list[dict]) -> list[dict]:
    """Dorar search pages repeat some entries; keep one per scholar + book + number + text."""
    seen, out = set(), []
    for c in cards:
        k = (c.get("scholar", ""), c.get("book", ""), c.get("number", "").split("/")[-1].strip(), normalize_ar(c.get("text", "")))
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out


def parse_explain(page: str) -> dict:
    body = _text(page)
    stops = _LABELS
    return {
        "text": body.split("الراوي")[0].strip() if "الراوي" in body else "",
        "narrator": _field(body, "الراوي", stops), "scholar": _field(body, "المحدث", stops),
        "book": _field(body, "المصدر", stops), "number": _field(body, "الصفحة أو الرقم", stops),
        "grade": _field(body, "خلاصة حكم المحدث", stops).strip("[]"),
        "takhrij": _field(body, "التخريج", stops),
        "sharh": body.split("شرح الحديث :", 1)[1].strip() if "شرح الحديث :" in body else "",
    }


_PUA = re.compile(r"[-ﭐ-﷿ﹰ-﻿]")  # Qur'an glyph font characters


def parse_tafseer(page: str) -> dict:
    """Section page of موسوعة التفسير: title (ayah range) and the tafsir body."""
    title = re.search(r"<title>([^<]+)</title>", page)
    title_t = re.sub(r"\s+", " ", htmllib.unescape(title.group(1))).replace("الدرر السنية - موسوعة التفسير -", "").strip() if title else ""
    m = re.search(r"الآيات\s*\((\d+)\s*-\s*(\d+)\)|الآية\s*\((\d+)\)", title_t)
    rng = (int(m.group(1)), int(m.group(2))) if m and m.group(1) else ((int(m.group(3)),) * 2 if m and m.group(3) else None)
    body = _text(page)
    # the tafsir body starts at the first heading followed by a colon (menu entries have none)
    starts = [body.find(h) for h in ("غريب الكلمات:", "مشكل الإعراب:", "المعنى الإجمالي:", "تفسير الآيات:") if body.find(h) >= 0]
    start = min(starts) if starts else 0
    text = _PUA.sub(" ", body[start:])
    text = re.sub(r"\[\d+\]\s*", " ", text)
    text = re.sub(r"يُنظر:\s*(?:\(\([^)]*\)\)[^،.()]*?(?:\([^)]*\))?[،.]?\s*)+", " ", text)
    text = re.sub(r"\(\([^)]*\)\)\s*(?:لابن [^\s(]+|للبيضاوي|للزمخشري)?\s*(?:\([^)]*\))?\s*[،.]?", " ", text)
    for end in ["بحث المواقع العلمية", "تابعنا", "الاشتراك في القائمة البريدية", "اختر السورة", "المراجع والمصادر", "جميع الحقوق محفوظة"]:
        k = text.find(end, 200)
        if k > 0:
            text = text[:k]
    return {"title": title_t, "range": rng, "text": re.sub(r"\s+", " ", text).strip()}


# ---------------------------------------------------------------------------------------------
class DorarClient:
    def __init__(self, transport: httpx.BaseTransport | None = None, cache: bool = True) -> None:
        self._http = httpx.Client(timeout=_TIMEOUT, follow_redirects=True, headers=_UA, transport=transport)
        self._use_cache = cache

    # --- cache (source_cache table) ---
    def _cache_get(self, key: str) -> dict | None:
        if not self._use_cache:
            return None
        try:
            from . import db

            with db.get_conn() as conn:
                row = conn.execute("SELECT payload FROM source_cache WHERE key = %s", (key,)).fetchone()
            return row["payload"] if row else None
        except Exception:  # noqa: BLE001 - cache is best-effort
            return None

    def _cache_put(self, key: str, url: str, payload: dict) -> None:
        if not self._use_cache:
            return
        try:
            from psycopg.types.json import Jsonb

            from . import db

            with db.get_conn() as conn:
                conn.execute(
                    "INSERT INTO source_cache (key, source, url, payload) VALUES (%s, 'dorar', %s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET payload = EXCLUDED.payload, url = EXCLUDED.url, fetched_at = now()",
                    (key, url, Jsonb(payload)),
                )
        except Exception as e:  # noqa: BLE001
            log.warning("source_cache write skipped: %s", e)

    def _get(self, url: str, **params) -> str:
        r = self._http.get(url, params=params or None, headers={**_UA, "X-Requested-With": "XMLHttpRequest"})
        r.raise_for_status()
        return r.text

    # --- hadith ---
    @staticmethod
    def search_url(matn: str, words: int = 8) -> str:
        q = " ".join(re.sub(r"[^\w\s]", " ", strip_tashkeel(matn)).split()[:words])
        return f"{BASE}/hadith/search?q={quote(q)}"

    def search(self, matn: str, words: int = 8) -> list[dict]:
        q = " ".join(re.sub(r"[^\w\s]", " ", strip_tashkeel(matn)).split()[:words])
        key = f"hadith-search:{normalize_ar(q)}"
        hit = self._cache_get(key)
        if hit is not None:
            return hit.get("cards", [])
        cards = parse_cards(self._get(f"{BASE}/hadith/search", q=q))
        self._cache_put(key, self.search_url(matn, words), {"cards": cards})
        return cards

    def explain(self, xplain_id: str) -> dict:
        key = f"hadith-explain:{xplain_id}"
        hit = self._cache_get(key)
        if hit is not None:
            return hit
        data = parse_explain(self._get(f"{BASE}/hadith/explain/{xplain_id}"))
        data["url"] = f"{BASE}/hadith/explain/{xplain_id}"
        self._cache_put(key, data["url"], data)
        return data

    def rulings_for(self, matn: str, book_ar: str = "", number: str = "") -> dict:
        """The scholars' rulings on the matched hadith, most relevant first."""
        cards = self.search(matn)
        key = normalize_ar(matn)
        aliases = _BOOK_ALIASES.get(book_ar, [book_ar] if book_ar else [])

        def rank(c: dict) -> tuple:
            same_book = any(a and a in c["book"] for a in aliases)
            same_num = bool(number) and c["number"].split("/")[-1].strip() == number
            sim = fuzz.partial_ratio(normalize_ar(c["text"]), key) if c["text"] else 0
            return (-(same_book and same_num), -same_book, -sim)

        relevant = [c for c in _dedupe(cards) if fuzz.partial_ratio(normalize_ar(c["text"]), key) >= 70] or _dedupe(cards)[:3]
        relevant.sort(key=rank)
        best = relevant[0] if relevant else None
        return {"cards": relevant[:4], "best": best, "search_url": self.search_url(matn),
                "sharh_available": bool(best and best.get("xplain")) or any(c.get("xplain") for c in relevant[:4])}

    def sharh_for(self, matn: str, book_ar: str = "", number: str = "") -> dict | None:
        info = self.rulings_for(matn, book_ar, number)
        for c in ([info["best"]] if info["best"] else []) + info["cards"]:
            if c and c.get("xplain"):
                ex = self.explain(c["xplain"])
                if ex.get("sharh"):
                    return {"text": ex["sharh"], "url": ex["url"], "scholar": ex.get("scholar", ""), "book": ex.get("book", "")}
        return None

    # --- tafsir ---
    def tafseer_for(self, surah: int, ayah: int) -> dict | None:
        key = f"tafseer:{surah}:{ayah}"
        hit = self._cache_get(key)
        if hit is not None:
            return hit or None
        # sections are numbered 1..N per surah, each covering an ayah range; walk until the range contains the ayah
        for n in range(1, 120):
            url = f"{BASE}/tafseer/{surah}/{n}"
            try:
                sec = parse_tafseer(self._get(url))
            except httpx.HTTPStatusError:
                break
            if not sec["range"]:
                break
            lo, hi = sec["range"]
            if lo <= ayah <= hi:
                out = {"title": sec["title"], "text": sec["text"][:12000], "url": url}
                self._cache_put(key, url, out)
                return out
            if lo > ayah:
                break
        self._cache_put(key, f"{BASE}/tafseer/{surah}", {})
        return None


_client: DorarClient | None = None


def get_dorar() -> DorarClient:
    global _client
    if _client is None:
        _client = DorarClient()
    return _client


def set_dorar(client: DorarClient | None) -> None:
    global _client
    _client = client
