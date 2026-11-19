"""Conservative, evidence-linked TOTAL candidate selection for receipt benchmarks.

This is a reproducible *baseline*, not a financial-grade field extractor.
A selection is returned only if exactly one candidate amount is linked to a
standalone TOTAL or GRAND TOTAL label on its OCR line. Subtotals and totals
elsewhere in the document are never silently substituted.
"""
from __future__ import annotations

import re
from decimal import Decimal

from .sroie_benchmark import norm_amount, AMOUNT_TOKEN

LABEL = re.compile(r"(?i)\b(?:grand\s+total|total)\b\s*[:=\-]?\s*")
EXCLUDE = re.compile(r"(?i)\b(?:sub\s*total|subtotal|tax|vat|gst|change|discount|balance|rounding)\b")


def select_total(lines):
    """lines: OCR line dicts {text, bbox, confidence, line_id}; return candidate or abstain.

    Bbox is a detected line union, NOT independently verified word position.
    """
    candidates = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        raw = str(line.get("text") or "").strip()
        if not raw or EXCLUDE.search(raw):
            continue
        labels = list(LABEL.finditer(raw))
        if len(labels) != 1:
            continue
        label = labels[0]
        if raw[:label.start()].strip(" :-=\t"):
            continue
        tail = raw[label.end():]
        amounts = [match.group(0) for match in AMOUNT_TOKEN.finditer(tail)]
        if len(amounts) != 1:
            continue
        # Conservative baseline: isolated integers might be item counts, not money.
        # For formats without explicit decimal cents, abstain and request review.
        if not re.search(r"\.\d{2}$", amounts[0]):
            continue
        amount = norm_amount(amounts[0])
        if amount is None:
            continue
        candidates.append({
            "value": str(amount),
            "raw_text": raw,
            "line_id": line.get("line_id"),
            "bbox": line.get("bbox"),
            "ocr_confidence": line.get("confidence"),
            "evidence": "line_label_and_numeric_token",
            "verification": "provisional",
        })
    # Multiple possible TOTAL rows demand review, even if numeric value agrees.
    if len(candidates) != 1:
        return {"status": "abstain", "reason": "total_label_missing_or_ambiguous",
                "candidate_count": len(candidates)}
    return {"status": "candidate", **candidates[0]}


def tess_lines(data):
    """Group pytesseract image_to_data Output.DICT into source line boxes."""
    keys = ("block_num", "par_num", "line_num")
    count = len(data["text"])
    grouped = {}
    for i in range(count):
        text = str(data["text"][i] or "").strip()
        if not text:
            continue
        key = tuple(int(data[k][i]) for k in keys)
        left, top = int(data["left"][i]), int(data["top"][i])
        width, height = int(data["width"][i]), int(data["height"][i])
        try:
            confidence = float(data["conf"][i])
        except (ValueError, TypeError):
            confidence = -1
        entry = grouped.setdefault(key, {"words": [], "positions": [], "scores": []})
        entry["words"].append((left, text))
        entry["positions"].append((left, top, left + width, top + height))
        if confidence >= 0:
            entry["scores"].append(confidence / 100)
    out = []
    for key, entry in sorted(grouped.items(), key=lambda x: (min(p[1] for p in x[1]["positions"]), x[0])):
        boxes = entry["positions"]
        out.append({
            "line_id": ".".join(map(str, key)),
            "text": " ".join(text for _, text in sorted(entry["words"])),
            "bbox": [min(x[0] for x in boxes), min(x[1] for x in boxes),
                     max(x[2] for x in boxes), max(x[3] for x in boxes)],
            "confidence": sum(entry["scores"]) / len(entry["scores"]) if entry["scores"] else None,
        })
    return out


def evaluate_selected(selection, annotated_total):
    """Only candidate + exact money equality is a correct selected field."""
    truth = norm_amount(annotated_total)
    if truth is None:
        return "invalid_reference"
    if selection.get("status") != "candidate":
        return "abstained"
    try:
        observed = Decimal(selection["value"])
    except (ValueError, TypeError):
        return "wrong"
    return "correct" if observed == truth else "wrong"
