"""Fail-closed, zero-human handoff for LOCAL document extraction.

No claim of 100% OCR accuracy. In this pilot, human escalation is replaced
with a machine-readable, unresolved blocker ledger. Nothing is falsely
marked verified or financially approved. This is a *routing policy*, not an
OCR correction engine or an external job scheduler.
"""
from .review_triage import categorize_reasons

_MANDATORY_ITEM_FIELDS = ("service_name", "quantity", "unit_price", "line_total")
_FINANCIAL_DOC_TYPES = frozenset({
    "hospital_invoice", "clinic_invoice", "pharmacy_invoice", "medical_invoice"
})


def _blocker(record_id, field, reasons, *, raw=None, page=None, evidence_id=None):
    reasons = sorted({str(x) for x in reasons if x})
    return {
        "record_id": record_id,
        "field": field,
        "raw": raw,
        "page": page,
        "evidence_id": evidence_id,
        "reasons": reasons,
        "category": categorize_reasons(reasons),
        "resolution_state": "unresolved_machine_only",
        # NEVER imply a retry was performed unless it actually was.
        "automatic_retries_executed": 0,
    }


def apply_zero_human_policy(doc):
    """Retain every source finding but prohibit routing to a human queue.

    Critical: BLOCK nonverified output. In particular, a zero-length
    requires_human_review must never be interpreted as verified data.
    """
    if doc.get("automation_policy") == "zero_human_fail_closed":
        return doc

    source_queue = list(doc.get("requires_human_review") or [])
    unresolved = []
    for item in source_queue:
        unresolved.append(_blocker(item.get("record_id"), item.get("field"),
                          item.get("reasons") or ["unresolved_source_check"],
                          raw=item.get("raw"), page=item.get("page"),
                          evidence_id=item.get("evidence_id")))

    # Turn a legacy review flag into an explicitly UNRESOLVED machine flag,
    # never a successful verification. Scan for review flags that might have
    # been omitted from the legacy queue as well.
    groups = ("patient", "provider", "hospitalization")
    for name in groups:
        record = doc.get(name) or {}
        for field_name, field in record.items():
            if not isinstance(field, dict) or field.get("verification") != "needs_review":
                continue
            field["original_verification"] = "needs_review"
            field["verification"] = "machine_unresolved"
            if not any(x["field"] == field_name and x["record_id"] == doc.get("document_id", "") + ":" + name
                       for x in unresolved):
                unresolved.append(_blocker(doc.get("document_id", "") + ":" + name,
                                           field_name, field.get("review_reasons") or ["low_confidence"],
                                           raw=field.get("raw"), page=field.get("page"),
                                           evidence_id=field.get("evidence_id")))

    for group in ("invoices", "invoice_items", "medications", "diagnoses",
                  "laboratory_tests", "imaging", "procedures"):
        for record in doc.get(group) or []:
            for field_name, field in record.items():
                if not isinstance(field, dict) or field.get("verification") != "needs_review":
                    continue
                field["original_verification"] = "needs_review"
                field["verification"] = "machine_unresolved"
                if not any(x["field"] == field_name and x["record_id"] == record.get("id")
                           for x in unresolved):
                    unresolved.append(_blocker(record.get("id"), field_name,
                        field.get("review_reasons") or ["low_confidence"],
                        raw=field.get("raw"), page=field.get("page"),
                        evidence_id=field.get("evidence_id")))

    # A review queue built by legacy validation is not exhaustive for every
    # incomplete invoice item (e.g. an unreadable quantity without strict env).
    # Enforce every required financial row field in this opt-in policy.
    if doc.get("document_type") in _FINANCIAL_DOC_TYPES:
        for row in doc.get("invoice_items", []):
            for field_name in _MANDATORY_ITEM_FIELDS:
                field = row.get(field_name) or {}
                if field.get("status") == "extracted" and field.get("value") is not None:
                    continue
                if any(x["record_id"] == row.get("id") and x["field"] == field_name
                       for x in unresolved):
                    continue
                unresolved.append(_blocker(
                    row.get("id"), field_name,
                    ["required_financial_field_missing"],
                    raw=field.get("raw"), page=field.get("page"),
                    evidence_id=field.get("evidence_id")))
        if not doc.get("invoice_items"):
            invs = doc.get("invoices") or []
            rec_id = invs[0].get("id") if invs else doc.get("document_id")
            if not any(x["field"] == "invoice_items" for x in unresolved):
                unresolved.append(_blocker(rec_id,"invoice_items",
                                          ["invoice_rows_not_verified"]))

    # A document-level extraction error cannot be allowed through simply
    # because it does not have a field in the legacy review queue.
    for warning in doc.get("warnings", []):
        if warning.get("severity") != "error":
            continue
        kind = warning.get("kind", "unknown_error")
        unresolved.append(_blocker(doc.get("document_id"), "document_integrity",
                                   ["source_error:" + kind]))

    # Eliminate exact duplicates while preserving all different causes.
    seen = set()
    deduped = []
    for item in unresolved:
        key = (item["record_id"], item["field"], tuple(item["reasons"]))
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    doc["automation_policy"] = "zero_human_fail_closed"
    doc["machine_unresolved_checks"] = deduped
    doc["unresolved_machine_count"] = len(deduped)
    doc["requires_human_review"] = []
    doc["human_handoff_count"] = 0
    doc["extraction_ready"] = not deduped and doc.get("processing_status") != "failed"
    # Extraction-ready is NOT medical or financial approval.
    doc["financial_approval"] = False
    if doc.get("processing_status") != "failed":
        doc["processing_status"] = ("completed" if doc["extraction_ready"]
                                     else "blocked_unresolved")
    return doc


def record_machine_issue(doc, field, reason):
    """Record a newly discovered machine blocker *after* initial validation."""
    ledger = doc.setdefault("machine_unresolved_checks", [])
    issue = _blocker(doc.get("document_id"), field, [reason])
    if not any(x.get("field") == field and reason in x.get("reasons", [])
               for x in ledger):
        ledger.append(issue)
    doc["unresolved_machine_count"] = len(ledger)
    doc["extraction_ready"] = False
    doc["financial_approval"] = False
    doc["human_handoff_count"] = 0
    doc["requires_human_review"] = []
    if doc.get("processing_status") != "failed":
        doc["processing_status"] = "blocked_unresolved"
    return doc
