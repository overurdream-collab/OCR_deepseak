"""Source-faithful correction of OCR spacing in medical service names.

We only add/remove spaces when the complete observed character sequence
remains IDENTICAL. Never repair names of patients, prices, IDs, diagnoses,
drugs' dose or uncertain Arabic yeh/kaf by guesswork.
"""
import re

# A tiny, intentionally conservative general medical-services vocabulary.
# Not imported from any synthetic invoice ground-truth/answer table.
_TERMS_AR = frozenset({
    "تحليل", "دم", "شامل", "تخطيط", "قلب", "وظائف", "سكر", "صائم",
    "أشعة", "سينية", "أجرة", "غرفة", "رسوم", "تمريض", "جلسة", "علاج",
    "طبيعي", "فوق", "موجات", "صوتية", "كشف", "استشاري",
    "أقراص", "كبسولات", "باراسيتامول", "أموكسيسيلين",
})


def _split_joined_arabic(token):
    if token in _TERMS_AR or not re.fullmatch(r"[\u0621-\u064a]+", token):
        return None
    splits = [(token[:i], token[i:]) for i in range(2, len(token) - 1)
              if token[:i] in _TERMS_AR and token[i:] in _TERMS_AR]
    # If multiple plausible segmentations exist, preserve source verbatim.
    return splits[0] if len(splits) == 1 else None


def repair_service_spacing(value):
    """Repair only provable boundaries; preserve every printed character."""
    if not isinstance(value, str) or not value.strip():
        return value
    original = value
    pieces = value.split(" ")
    merged = []
    i = 0
    while i < len(pieces):
        tok = pieces[i]
        if (i + 1 < len(pieces)
                and tok not in _TERMS_AR and pieces[i + 1] not in _TERMS_AR
                and tok + pieces[i + 1] in _TERMS_AR):
            merged.append(tok + pieces[i + 1])
            i += 2
            continue
        merged.append(tok)
        i += 1
    result = []
    for token in merged:
        split = _split_joined_arabic(token)
        if split:
            result.extend(split)
        elif re.fullmatch(r"[A-Za-z]+", token):
            # CamelCase boundary ONLY: preserves every Latin letter and case.
            result.append(re.sub(r"(?<=[a-z])(?=[A-Z])", " ", token))
        else:
            result.append(token)
    candidate = " ".join(result)
    if candidate.replace(" ", "") != original.replace(" ", ""):
        return original
    return candidate


def repair_document_service_names(document):
    """Adjust value, never source raw/evidence; no new rows or inferred words."""
    for item in document.get("invoice_items", []):
        field = item.get("service_name") or {}
        if field.get("status") != "extracted" or not field.get("evidence_id"):
            continue
        if not isinstance(field.get("raw"), str) or not isinstance(field.get("value"), str):
            continue
        current = field["value"]
        improved = repair_service_spacing(current)
        if improved == current or current.replace(" ", "") != improved.replace(" ", ""):
            continue
        field["value"] = improved
        field["spacing_repair"] = {
            "type": "observed_glyphs_whitespace_only",
            "original_value": current,
        }
    return document
