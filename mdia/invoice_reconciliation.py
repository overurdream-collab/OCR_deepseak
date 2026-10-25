"""Evidence-first invoice reconciliation. Never change original OCR values."""
from decimal import Decimal, InvalidOperation
from collections import Counter

def number(value):
    if value is None or isinstance(value, bool):
        return None
    raw = str(value).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,"))
    raw = raw.replace(",", "").strip()
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None

def reconcile(rows, source_tokens):
    """Return non-authoritative review findings. source_tokens are OCR text spans."""
    tokens = Counter(str(t).strip() for t in source_tokens if str(t).strip())
    findings = []
    for i, row in enumerate(rows):
        reasons = []
        for field in ("description", "quantity", "unit_price", "line_total"):
            value = row.get(field)
            if value is None or not str(value).strip():
                reasons.append("missing_" + field)
            elif field == "description":
                if not any(str(value).strip() in token for token in tokens):
                    reasons.append("no_source_evidence_" + field)
            else:
                expected = number(value)
                if expected is None or not any(number(token) == expected for token in tokens):
                    reasons.append("no_source_evidence_" + field)
        q, p, total = (number(row.get(k)) for k in ("quantity", "unit_price", "line_total"))
        if all(x is not None for x in (q, p, total)) and q * p != total:
            reasons.append("arithmetic_mismatch")
        findings.append({"row_index": i, "review_required": bool(reasons),
                         "reasons": reasons, "original_row": dict(row)})
    return findings
