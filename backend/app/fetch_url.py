"""URL tab: fetch a public post/article and extract the quoted hadith/text from it.

Supported: X/Twitter posts (public fxtwitter JSON API), sunnah.com hadith pages, and generic
public articles (densest Arabic/Latin text block, preferring blocks that quote the Prophet ﷺ).
Instagram, Facebook, YouTube and TikTok require authentication and are reported as unreachable."""
from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup


class URLError(Exception):
    pass


_UNSUPPORTED = ("instagram.com", "facebook.com", "fb.com", "fb.watch", "youtube.com", "youtu.be", "tiktok.com")
_UA = "Mozilla/5.0 (compatible; Tahaqqaq/0.1; +https://github.com/)"
_AR = re.compile(r"[؀-ۿ]")
_MARKERS = re.compile(r"(قال رسول الله|قال النبي|صلى الله عليه وسلم|ﷺ|عليه الصلاة والسلام|عن النبي|the prophet|messenger of allah|narrated|hadith)", re.IGNORECASE)
_SENT_SPLIT = re.compile(r"(?<=[.!؟?»\"”])\s+|\n+")


def _normalize(url: str) -> str:
    url = url.strip()
    if re.match(r"^(?:[a-z][a-z0-9+.-]*://|javascript:|mailto:|data:|file:|tel:|sms:)", url, re.I) and not re.match(r"^https?://", url, re.I):
        raise URLError("only http and https links are supported")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    if not re.match(r"^https?://[^/\s]+(:\d+)?(/|$)", url, re.I) or " " in url:
        raise URLError("not a valid link")
    return url


def extract(url: str, max_chars: int = 2000, lang: str = "ar") -> tuple[str, str]:
    """Return (quote, context): the text to verify and the surrounding extracted text. `lang` is the interface
    language: a page carrying both (sunnah.com) gives the Arabic text in Arabic and its English translation in English."""
    url = _normalize(url)
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if any(host == d or host.endswith("." + d) for d in _UNSUPPORTED):
        raise URLError(f"{host} requires login; paste the text or a screenshot instead")
    if host in ("x.com", "twitter.com", "mobile.twitter.com"):
        text = _tweet(url)
        return pick_quote(text)[:max_chars], text[:max_chars]
    try:
        with httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": _UA}) as c:
            r = c.get(url)
            r.raise_for_status()
    except (httpx.HTTPError, httpx.InvalidURL, ValueError) as e:
        raise URLError(str(e)) from e
    ctype = (r.headers.get("content-type") or "").lower()
    if ctype and "html" not in ctype and "text" not in ctype and "xml" not in ctype:
        raise URLError("the link is not a web page")
    soup = BeautifulSoup(r.text, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript", "form", "aside", "button", "svg"]):
        tag.decompose()

    if host == "sunnah.com":
        found = sunnah_texts(soup, lang)
        if found:
            return found[0][:max_chars], found[1][:max_chars]

    main = _main_text(r.text, soup)
    if len(main) < 10:
        og = soup.find("meta", attrs={"property": "og:description"}) or soup.find("meta", attrs={"name": "description"})
        main = _clean(og.get("content", "")) if og else ""
    if len(main) < 10:
        raise URLError("no readable text at that URL")
    # the pipeline finds the quoted/attributed segments in `main`, verifies each and keeps the best
    return main[:max_chars], main[:max_chars]


def _main_text(html: str, soup: BeautifulSoup) -> str:
    """Main-content extraction: trafilatura, then readability-lxml, then the densest leaf blocks."""
    try:
        import trafilatura

        t = trafilatura.extract(html, include_comments=False, include_tables=True, favor_recall=True) or ""
        if len(t.strip()) >= 40:
            return _clean(t)
    except Exception:  # noqa: BLE001
        pass
    try:
        from readability import Document

        frag = Document(html).summary(html_partial=True)
        t = BeautifulSoup(frag, "lxml").get_text("\n", strip=True)
        if len(t.strip()) >= 40:
            return _clean(t)
    except Exception:  # noqa: BLE001
        pass
    blocks = _leaf_blocks(soup)
    if not blocks:
        return ""
    blocks.sort(key=_block_score, reverse=True)
    return "\n".join(blocks[:6])


def sunnah_texts(soup: BeautifulSoup, lang: str) -> tuple[str, str] | None:
    """(quote, context) of a sunnah.com hadith page: the Arabic saying, or the English translation in English."""
    ar_el = soup.select_one(".arabic_text_details") or soup.select_one(".arabic_hadith_full")
    en_el = soup.select_one(".english_hadith_full") or soup.select_one(".text_details")
    ar = _clean(ar_el.get_text(" ", strip=True)) if ar_el else ""
    en = re.sub(r"\s+", " ", en_el.get_text(" ", strip=True)).strip() if en_el else ""
    quote = en if lang == "en" and en else ar
    if not quote:
        return None
    other = ar if quote == en else en
    return quote, quote + ("\n" + other if other else "")


def extract_text(url: str, max_chars: int = 2000, lang: str = "ar") -> str:
    return extract(url, max_chars, lang)[0]


def _clean(t: str) -> str:
    return re.sub(r"[ \t]+", " ", t).strip()


def _leaf_blocks(soup: BeautifulSoup) -> list[str]:
    out = []
    for el in soup.find_all(["p", "div", "blockquote", "li", "span", "td", "article", "section"]):
        if el.find(["p", "div", "li", "blockquote", "article", "section"]):
            continue  # not a leaf block
        t = _clean(el.get_text(" ", strip=True))
        if 15 <= len(t) <= 1200:
            out.append(t)
    return out


def _block_score(t: str) -> float:
    ar = len(_AR.findall(t))
    latin = len(re.findall(r"[A-Za-z]", t))
    letters = ar + latin
    if letters == 0:
        return 0.0
    score = float(min(len(t), 600))
    if _MARKERS.search(t):
        score *= 2.0
    # prefer Arabic content (the sources are Arabic); penalise link-heavy / menu-like blocks
    score *= 1.0 + ar / max(letters, 1)
    if t.count("|") > 3 or t.count("·") > 3:
        score *= 0.5
    return score


def pick_quote(text: str) -> str:
    """From a block of text, keep the sentence(s) most likely to be the quoted hadith/verse."""
    text = _clean(text)
    sents = [s.strip() for s in _SENT_SPLIT.split(text) if s and s.strip()]
    if len(sents) <= 1 or len(text) <= 300:
        return text
    marked = [s for s in sents if _MARKERS.search(s)]
    pool = marked or sents
    best = max(pool, key=lambda s: min(len(s), 400) * (1.5 if _AR.search(s) else 1.0))
    # include the following sentence when the marker sentence is just the attribution
    if len(best) < 40 and best in sents:
        i = sents.index(best)
        if i + 1 < len(sents):
            best = best + " " + sents[i + 1]
    return best


def _tweet(url: str) -> str:
    m = re.search(r"(?:x|twitter)\.com/([^/]+)/status/(\d+)", url)
    if not m:
        raise URLError("not a post URL")
    api = f"https://api.fxtwitter.com/{m.group(1)}/status/{m.group(2)}"
    try:
        with httpx.Client(timeout=15, headers={"User-Agent": _UA}) as c:
            r = c.get(api)
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise URLError(str(e)) from e
    text = (data.get("tweet") or {}).get("text") or ""
    if not text:
        raise URLError("post has no text")
    return text
