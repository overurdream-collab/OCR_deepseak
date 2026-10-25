"""Conservative, independent invoice evidence checks.

This validator never creates or changes a charge or an OCR field. It tests
whether the ORIGINAL OCR source for a particular field contains the claimed
value and whether SAME-ROW fields share plausible page geometry. A page-global
token occurrence is not evidence of a charge. All check outcomes remain
review annotations; line-interpolated OCR boxes are NOT independently verified.
"""
from decimal import Decimal, InvalidOperation
import re
import unicodedata

from .textutil import match_key, parse_number


def _normalized(s):
    return unicodedata.normalize("NFKC", str(s or "")).translate(
        str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬", "01234567890123456789.,"))


def number(value):
    if value is None or isinstance(value, bool):
        return None
    s = _normalized(value).strip()
    # Match an entire numeric token, not a number embedded in prose.
    if not re.fullmatch(r"[-+]?(?:\d+(?:[,.]\d+)*|\(\d+(?:[,.]\d+)*\))", s):
        return None
    try:
        return parse_number(s)
    except (InvalidOperation, ValueError, TypeError):
        return None


def _numeric_in_source(value, source):
    wanted = number(value)
    if wanted is None:
        return False
    for m in re.finditer(r"(?<![\d])[-+]?\(?\d[\d.,]*\)?(?![\d])",
                         _normalized(source)):
        if number(m.group()) == wanted:
            return True
    return False


def _text_in_source(value, source):
    requested = match_key(_normalized(value))
    printed = match_key(_normalized(source))
    return bool(requested and requested in printed)


def _bbox(box):
    return (isinstance(box, (list, tuple)) and len(box) == 4 and
            all(isinstance(v, (float, int)) and not isinstance(v, bool)
                and 0 <= v <= 1 for v in box)
            and box[0] < box[2] and box[1] < box[3])


def _row_checks(item, evidence):
    """Audit one row using the field's OWN evidence ID, not all page tokens."""
    reasons, geometries = {}, {}
    for key in ("service_name", "quantity", "unit_price", "line_total"):
        field = item.get(key, {})
        issues = []
        if not isinstance(field, dict) or field.get("status") != "extracted" or field.get("raw") is None:
            reasons[key] = ["missing_extracted_value"]
            continue
        e = evidence.get(field.get("evidence_id"))
        if not e:
            reasons[key] = ["missing_linked_evidence"]
            continue
        b = e.get("bbox")
        if not _bbox(b) or field.get("page") != e.get("page"):
            issues.append("invalid_source_location")
        else:
            geometries[key] = (field.get("page"), b)
        source = e.get("text") or ""
        exists = (_text_in_source(field["raw"], source) if key == "service_name"
                  else _numeric_in_source(field["raw"], source))
        if not exists:
            issues.append("value_not_in_linked_source")
        if e.get("geometry_source") == "line_interpolated":
            issues.append("estimated_word_location")
        # Don't say 'verified' for ANY machine prediction: geometry is a hint only.
        if issues:
            reasons[key] = issues

    anchor = geometries.get("service_name")
    if anchor:
        ap, ab = anchor
        ay = (ab[1] + ab[3]) / 2
        for key in ("quantity", "unit_price", "line_total"):
            if key in geometries:
                bp, bb = geometries[key]
                by = (bb[1] + bb[3]) / 2
                if ap != bp or abs(ay - by) > 0.035:
                    reasons.setdefault(key, []).append("cross_row_geometry")
    q, p, t = (number((item.get(key) or {}).get("raw"))
               for key in ("quantity", "unit_price", "line_total"))
    discount = number((item.get("discount") or {}).get("raw"))
    if all(v is not None for v in (q, p, t)) and q * p != t:
        # A valid printed discount may explain the difference; keep that
        # separate from unsupported arithmetic and let existing validator decide.
        if discount is None or not (q*p-discount == t or q*p*(1-discount/Decimal(100)) == t):
            for key in ("quantity", "unit_price", "line_total"):
                reasons.setdefault(key, []).append("arithmetic_mismatch")
    return reasons


def review_document_evidence(doc):
    """Return {record_id, field_reasons}; safe and read-only."""
    evs = {e.get("id"): e for e in doc.get("evidence", [])
           if isinstance(e, dict) and e.get("id")}
    return [{"record_id": item.get("id"), "field_reasons": reasons}
            for item in doc.get("invoice_items", [])
            if (reasons := _row_checks(item, evs))]


def reconcile(rows, source_tokens):
    """Legacy non-authoritative single-row heuristic kept for compatibility.

    Not suitable for financial acceptance because tokens are not linked to rows.
    Use review_document_evidence() in the production validation path.
    """
    tokens = [str(t).strip() for t in source_tokens if str(t).strip()]
    findings = []
    for i, row in enumerate(rows):
        reasons = []
        for field in ("description", "quantity", "unit_price", "line_total"):
            value = row.get(field)
            if value is None or not str(value).strip():
                reasons.append("missing_" + field)
            elif field == "description":
                if not any(_text_in_source(value, token) for token in tokens):
                    reasons.append("no_source_evidence_" + field)
            elif not any(_numeric_in_source(value, token) for token in tokens):
                reasons.append("no_source_evidence_" + field)
        q, p, total = (number(row.get(k)) for k in ("quantity", "unit_price", "line_total"))
        if all(x is not None for x in (q, p, total)) and q*p != total:
            reasons.append("arithmetic_mismatch")
        findings.append({"row_index": i, "review_required": bool(reasons),
                         "reasons": reasons, "original_row": dict(row)})
    return findings
