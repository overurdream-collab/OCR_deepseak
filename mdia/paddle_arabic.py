"""Opt-in Arabic/English OCR using PaddleOCR 3.x PP-OCRv5 multilingual recognition.

NOT enabled by default. Detection rectangles are LINE-level; per-token x positions
are INTERPOLATED and must not be presented as independently verified word boxes.
No network/model dependencies are loaded unless this backend is explicitly used.
"""
import json
import math
import re
from functools import lru_cache

from .model import Word
from .textutil import has_ar, nfkc

MODEL_NAME = 'arabic_PP-OCRv5_mobile_rec'
DETECTION_NAME = 'PP-OCRv5_mobile_det'


@lru_cache(maxsize=1)
def _load_model():
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise RuntimeError('PaddleOCR is not installed; install paddlepaddle>=3 and paddleocr>=3') from exc
    return PaddleOCR(
        text_detection_model_name=DETECTION_NAME,
        text_recognition_model_name=MODEL_NAME,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        device='cpu',
    )


def _plain(value):
    if hasattr(value, 'tolist'):
        return value.tolist()
    return value


def _payload(item):
    obj = getattr(item, 'json', item)
    if callable(obj):
        obj = obj()
    if isinstance(obj, str):
        obj = json.loads(obj)
    if not isinstance(obj, dict):
        raise ValueError('Unsupported PaddleOCR result object; missing JSON mapping')
    obj = obj.get('res', obj)
    if not isinstance(obj, dict):
        raise ValueError('PaddleOCR result has no valid res mapping')
    return obj


def _bbox(value, width, height):
    coords = _plain(value)
    if not isinstance(coords, (tuple, list)) or not coords:
        raise ValueError('Missing OCR detection coordinates; cannot create evidence')
    if len(coords) == 4 and all(isinstance(n, (float, int)) for n in coords):
        x0, y0, x1, y1 = coords
    elif len(coords) >= 3 and all(isinstance(x, (tuple, list)) and len(x) >= 2 for x in coords):
        x0 = min(float(p[0]) for p in coords)
        y0 = min(float(p[1]) for p in coords)
        x1 = max(float(p[0]) for p in coords)
        y1 = max(float(p[1]) for p in coords)
    else:
        raise ValueError('Malformed OCR detection coordinates')
    if not all(math.isfinite(float(n)) for n in (x0, y0, x1, y1)):
        raise ValueError('Non-finite detection coordinates')
    x0, y0, x1, y1 = float(x0), float(y0), float(x1), float(y1)
    if x0 >= x1 or y0 >= y1:
        raise ValueError('Invalid rectangle ordering')
    return [min(1., max(0., x0 / width)), min(1., max(0., y0 / height)),
            min(1., max(0., x1 / width)), min(1., max(0., y1 / height))]


def _repair_labeled_line(text):
    """Restore legible Arabic label/value order without inventing missing data.

    OCR tokens remain approximate locations and require human review.
    """
    invoice = re.fullmatch(r"([A-Za-z]{2,5}-[0-9]{2,12})\s*[:：]\s*رقم\s+الفاتورة", text)
    if invoice:
        return "رقم الفاتورة: " + invoice.group(1)
    return re.sub(r"(اسم\s+المريض)(?=[\u0621-\u064a])", r"\1 ", text)


def result_to_words(result, image_size):
    """Adapt official OCRResult rec_texts/scores/boxes to MDIA Word objects.

    Recognition is performed at detected LINE granularity. Token boxes are
    proportional ESTIMATES, not trustworthy per-token geometric evidence.
    Every caller must visibly mark the page for human review.
    """
    width, height = image_size
    if width <= 0 or height <= 0:
        raise ValueError('Invalid input image dimensions')
    words = []
    for item in result:
        data = _payload(item)
        texts = _plain(data.get('rec_texts', []))
        scores = _plain(data.get('rec_scores', []))
        boxes = data.get('rec_boxes', None)
        if boxes is None:
            boxes = data.get('rec_polys', None)
        boxes = _plain(boxes)
        if not isinstance(texts, list) or not isinstance(scores, list) or not isinstance(boxes, list):
            raise ValueError('Incomplete PaddleOCR text, confidence or geometry arrays')
        if len(texts) != len(scores) or len(texts) != len(boxes):
            raise ValueError('Misaligned PaddleOCR recognition/geometry arrays')
        for text, score, bounds in zip(texts, scores, boxes):
            text = _repair_labeled_line(nfkc(str(text).strip()))
            if not text:
                continue
            confidence = float(score)
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError('Invalid recognition confidence')
            box = _bbox(bounds, width, height)
            if box[0] >= box[2] or box[1] >= box[3]:
                raise ValueError('Detected box outside input image')
            tokens = re.findall(r'\S+', text)
            total = sum(len(tok) for tok in tokens) + max(0, len(tokens) - 1)
            consumed = 0
            rtl = has_ar(text) and sum(has_ar(t) for t in tokens) > len(tokens) / 2
            for tok in tokens:
                start = consumed / total
                end = (consumed + len(tok)) / total
                a, b = (1 - end, 1 - start) if rtl else (start, end)
                x0 = box[0] + (box[2] - box[0]) * a
                x1 = box[0] + (box[2] - box[0]) * b
                # The box field is deliberately unset: it would falsely imply
                # an independently localized word. Position is an estimate.
                words.append(Word(tok, x0, box[1], x1, box[3], confidence, 'ocr', rtl_hint=rtl))
                consumed += len(tok) + 1
    return words


def ocr_image(image):
    """Real PaddleOCR inference. No silent Tesseract substitution."""
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError('numpy is required for PaddleOCR inference') from exc
    image = image.convert('RGB')
    output = _load_model().predict(np.asarray(image))
    return result_to_words(output, image.size)
