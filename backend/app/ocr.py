"""OCR for the image tab.

Default: Tesseract (ara+eng, tessdata_best models baked into the Docker image), run twice
(ara+eng / ara-only) keeping the pass with more Arabic, then line-level junk filtering.
Optional: when ANTHROPIC_API_KEY is set, Claude vision transcribes the image instead, which is far
more reliable on diacritised or decorative Arabic. Either way the result is only a transcription;
verification happens afterwards against the sources."""
from __future__ import annotations

import io
import re

from PIL import Image, ImageOps

from .config import get_settings

_AR = re.compile(r"[؀-ۿ]")
_LAT = re.compile(r"[A-Za-z]")


class OCRError(Exception):
    pass


def _prepare(data: bytes) -> list[Image.Image]:
    """OpenCV preprocessing: grayscale, 2x upscale, deskew, adaptive threshold.
    Returns two variants (binarised and plain grayscale); Tesseract runs on both and the
    pass with more real words wins, because adaptive thresholding helps photos but can hurt
    clean screenshots."""
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("L")
    except Exception as e:  # noqa: BLE001
        raise OCRError(f"unreadable image: {e}") from e
    try:
        import cv2
        import numpy as np

        g = np.array(img)
        scale = 2.0 if g.shape[1] < 2400 else 1.0
        if scale != 1.0:
            g = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        g = _deskew(g, cv2, np)
        binar = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)
        return [Image.fromarray(binar), Image.fromarray(g)]
    except ImportError:  # pragma: no cover - OpenCV missing: plain Pillow upscale
        if img.width < 1600:
            s = 1600 / img.width
            img = img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS)
        return [img]


def _deskew(g, cv2, np):
    """Rotate by the dominant text angle (only when it is clearly off-axis, up to 15°)."""
    inv = cv2.bitwise_not(cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1])
    pts = cv2.findNonZero(inv)
    if pts is None or len(pts) < 500:
        return g
    angle = cv2.minAreaRect(pts)[-1]
    if angle < -45:
        angle += 90
    elif angle > 45:
        angle -= 90
    if abs(angle) < 0.5 or abs(angle) > 15:
        return g
    h, w = g.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(g, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


_KEEP_PUNCT = re.compile(r"[\d٠-٩]+[.،:]?|[.,،:؛!؟«»()\"“”'‘’\-–—]+")
_TASHKEEL_RE = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_BIDI = re.compile(r"[‎‏‪-‮⁦-⁩]")


def _junk_line(line: str) -> bool:
    """A line Tesseract produced from the diacritics band of vocalised text: mostly 1-2 letter fragments
    and stray digits/marks (e.g. «باض ا وسس؟ ادق قي ردس ااي سا سا سردي فر 2 ار ١ ان م ا»)."""
    toks = line.split()
    if len(toks) < 6:
        return False
    letters = [len(re.sub(r"[\W\d_]", "", _TASHKEEL_RE.sub("", t))) for t in toks]
    short = sum(1 for n in letters if n <= 2)
    tiny = sum(1 for t, n in zip(toks, letters, strict=True) if n <= 1 or re.fullmatch(r"[\d٠-٩]+", t))
    return short >= 0.5 * len(toks) and tiny >= 2


def clean_lines(text: str) -> str:
    """Drop Latin junk tokens inside Arabic-majority lines, diacritics-band junk lines and bidi marks;
    keep real English lines and quotation marks (they delimit the quoted saying)."""
    out: list[str] = []
    for line in _BIDI.sub("", text).splitlines():
        line = line.strip()
        if not line:
            out.append("")
            continue
        ar, la = len(_AR.findall(line)), len(_LAT.findall(line))
        if ar and ar >= 0.4 * (ar + la):
            if _junk_line(line):
                continue
            toks = [t for t in line.split() if _AR.search(t) or _KEEP_PUNCT.fullmatch(t)]
            line = " ".join(toks)
        elif la and la < 4 and not ar:
            continue  # stray characters
        if line:
            out.append(line)
    return "\n".join(out).strip()


def reflow(text: str) -> str:
    """Join visual line breaks (OCR follows the image's line wrapping, not sentences) into flowing text;
    blank lines stay paragraph breaks."""
    out: list[str] = []
    for para in re.split(r"\n\s*\n", text.strip()):
        joined = ""
        for line in (ln.strip() for ln in para.splitlines()):
            if not line:
                continue
            if joined.endswith("-") and line[:1].islower():  # English hyphenation
                joined = joined[:-1] + line
            else:
                joined = f"{joined} {line}" if joined else line
        if joined:
            out.append(re.sub(r"\s{2,}", " ", joined))
    return "\n\n".join(out)


def _tesseract(variants: list[Image.Image]) -> str:
    try:
        import pytesseract
    except ImportError as e:  # pragma: no cover
        raise OCRError("pytesseract not installed") from e
    results: list[tuple[int, str]] = []
    try:
        for i, img in enumerate(variants):
            a = clean_lines(pytesseract.image_to_string(img, lang="ara+eng", config="--psm 6"))
            results.append((_word_score(a) * 10 + (1 if i == 0 else 0), a))
            if i == 0:  # Arabic-only pass once (it turns English into junk, so it must win clearly)
                b = clean_lines(pytesseract.image_to_string(img, lang="ara", config="--psm 4"))
                results.append((int(_word_score(b) * 10 / 1.3), b))
    except pytesseract.TesseractNotFoundError as e:
        raise OCRError("tesseract binary not found") from e
    except Exception as e:  # noqa: BLE001
        raise OCRError(str(e)) from e
    results.sort(key=lambda r: -r[0])
    return results[0][1]


def _word_score(text: str) -> int:
    n = 0
    for tok in re.findall(r"\S+", text):
        letters = re.sub(r"[^\w]", "", tok)
        if len(letters) < 3 or re.search(r"\d", letters):
            continue
        if _AR.fullmatch(letters) is None and _LAT.fullmatch(letters) is None:
            # mixed-script token: junk unless it's clean Arabic or clean Latin
            if not (re.fullmatch(r"[\u0600-\u06FF]+", letters) or re.fullmatch(r"[A-Za-z]+", letters)):
                continue
        n += 1
    return n


def extract_text(data: bytes, media_type: str = "image/png", use_ai: bool = True) -> str:
    get_settings()
    variants = _prepare(data)  # validates that the bytes are a real image before anything is sent anywhere
    text = ""
    from .llm import get_client, transcribe_image

    if use_ai and get_client().enabled:
        text = transcribe_image(data, media_type) or ""
    if not text:
        text = _tesseract(variants)
    text = reflow(clean_lines(text))
    if len(text) < 3:
        raise OCRError("no text found in image")
    return text
