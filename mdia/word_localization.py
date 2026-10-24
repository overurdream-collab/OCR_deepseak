"""EVIDENCE-01: optional SECOND OCR word geometry, never replacement OCR text.

Paddle returns word boxes interpolated from detected line rectangles. Matching
one word to a separately detected Tesseract word rectangle may improve the
location but is NOT ground-truth validation. All Paddle fields still require
human review.
"""
import math
import re
import unicodedata

DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def token_key(raw):
    text = unicodedata.normalize("NFKC", str(raw or "")).translate(DIGITS).casefold()
    text = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", text)
    return re.sub(r"[^a-z0-9\u0621-\u064a]", "", text)


def align_from_tesseract_data(words, data, image_size, min_confidence=80):
    """Match exact token, high confidence, correct row/X, and unique word only.

    Never edit Paddle recognized text, dosage, value or confidence. If ANY
    condition fails, the word stays line_interpolated.
    """
    width, height = image_size
    if width <= 0 or height <= 0:
        raise ValueError("invalid image dimensions")
    keys = ("text", "conf", "left", "top", "width", "height")
    if not isinstance(data, dict) or any(k not in data for k in keys):
        raise ValueError("Tesseract word data incomplete")
    length = len(data["text"])
    if any(len(data[k]) != length for k in keys):
        raise ValueError("Tesseract word data arrays misaligned")
    candidates = []
    for i in range(length):
        key = token_key(data["text"][i])
        try:
            conf = float(data["conf"][i])
            x, y, w, h = (float(data[k][i]) for k in ("left", "top", "width", "height"))
        except (TypeError, ValueError):
            continue
        if not key or not math.isfinite(conf) or conf < min_confidence:
            continue
        if not all(math.isfinite(t) for t in (x, y, w, h)) or w <= 0 or h <= 0:
            continue
        box = [x / width, y / height, (x + w) / width, (y + h) / height]
        if any(t < 0 or t > 1 for t in box):
            continue
        candidates.append((key, box))
    claimed = set()
    for word in words:
        if getattr(word, "geometry_source", "") != "line_interpolated":
            continue
        key = token_key(word.text)
        if len(key) < 2:
            continue
        matches = []
        for i, (ckey, box) in enumerate(candidates):
            if key != ckey or i in claimed:
                continue
            y_intersection = max(0., min(word.y1, box[3]) - max(word.y0, box[1]))
            if y_intersection < 0.5 * min(word.y1 - word.y0, box[3] - box[1]):
                continue
            xc = (box[0] + box[2]) / 2
            if abs(xc - word.cx) > max(0.018, min(0.06, (word.x1 - word.x0) * 1.5)):
                continue
            matches.append((i, box))
        if len(matches) != 1:
            continue
        i, box = matches[0]
        claimed.add(i)
        word.box = box
        word.geometry_source = "cross_engine_word_match"
    return words


def align_with_tesseract(image, words):
    """Explicit opt-in, requires local Tesseract Arabic+English word OCR."""
    import pytesseract
    data = pytesseract.image_to_data(
        image.convert("RGB"), lang="ara+eng", config="--psm 11",
        output_type=pytesseract.Output.DICT)
    return align_from_tesseract_data(words, data, image.size)
