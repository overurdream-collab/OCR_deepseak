"""Safe bridge from MDIA OCR output to the invoice review work queue.

MDIA specializes in medical documents. It does not validate supplier PO / GRN
identity and cannot grant financial authenticity. This bridge NEVER promotes
OCR fields to verified financial data, even if MDIA labels a field auto_verified.
"""
from __future__ import annotations

import hashlib
import json


def _review_field(field: object, evidence: dict, source_digest: str) -> dict:
    if not isinstance(field, dict):
        return {"status": "unverifiable", "reason": "missing/invalid extraction"}
    ref = field.get("evidence_id")
    ev = evidence.get(ref) if isinstance(ref, str) else None
    raw = field.get("raw")
    if not isinstance(raw, str) or not raw or not isinstance(ev, dict):
        return {"status": "unverifiable", "reason": "missing original text or evidence"}
    page = field.get("page")
    if not isinstance(page, int) or page != ev.get("page"):
        return {"status": "unverifiable", "reason": "source page mismatch"}
    if ev.get("matched_text") != raw:
        return {"status": "unverifiable", "reason": "evidence text mismatch"}
    return {
        "status": "needs_human_review",
        "raw": raw,
        "value_suggestion": field.get("value"),
        "mdia_verification": field.get("verification"),
        "evidence_id": ref,
        "source_sha256": source_digest,
        "page": page,
        "bbox": ev.get("bbox"),
        "geometry_source": ev.get("geometry_source"),
        "source_line": ev.get("text"),
        "reason": "OCR/text-layer extraction is not proof of supplier-authenticated value",
    }


def prepare_mdia_review(raw_pdf: bytes, mdia_result: dict) -> dict:
    """Prepare human-review candidates, never account or invoice approval.

    The raw PDF must be supplied by trusted storage and hashed again here.
    JSON inputs from unknown callers are untrusted.
    """
    if not isinstance(raw_pdf, bytes) or not raw_pdf.startswith(b"%PDF-"):
        raise ValueError("original PDF bytes required")
    if not isinstance(mdia_result, dict):
        raise ValueError("invalid MDIA result")
    digest = hashlib.sha256(raw_pdf).hexdigest()
    source = mdia_result.get("source")
    if not isinstance(source, dict) or source.get("sha256") != digest:
        return {"status": "UNVERIFIABLE", "approval": False,
                "source_sha256": digest, "reasons": ["MDIA result source hash mismatch"],
                "documents": []}
    documents = []
    for doc in mdia_result.get("documents", []):
        if not isinstance(doc, dict):
            raise ValueError("invalid MDIA document")
        evidence = {e.get("id"): e for e in doc.get("evidence", [])
                    if isinstance(e, dict) and isinstance(e.get("id"), str)}
        invoices = []
        for index, inv in enumerate(doc.get("invoices", [])):
            fields = {key: _review_field(value, evidence, digest)
                      for key, value in inv.items() if isinstance(value, dict)
                      and ("evidence_id" in value or "raw" in value)}
            invoices.append({"source_index": index, "fields": fields})
        lines = []
        for index, line in enumerate(doc.get("invoice_items", [])):
            fields = {key: _review_field(value, evidence, digest)
                      for key, value in line.items() if isinstance(value, dict)
                      and ("evidence_id" in value or "raw" in value)}
            lines.append({"source_index": index, "fields": fields})
        documents.append({"document_id": doc.get("document_id"),
                          "document_type": doc.get("document_type"),
                          "processing_status": doc.get("processing_status"),
                          "invoices": invoices, "invoice_items": lines,
                          "review_required": True})
    return {"status": "UNVERIFIABLE", "approval": False,
            "source_sha256": digest, "reasons": [
                "MDIA extraction is provisional; supplier/PO/GRN verification required"],
            "documents": documents}


def prepare_mdia_review_json(raw_pdf: bytes, result_json: bytes) -> dict:
    """Parse MDIA JSON without accepting non-finite numeric constants."""
    def reject_constant(value):
        raise ValueError(f"unsupported numeric constant: {value}")
    if not isinstance(result_json, bytes) or len(result_json) > 20_000_000:
        raise ValueError("MDIA result must be JSON bytes <= 20 MB")
    return prepare_mdia_review(raw_pdf, json.loads(result_json.decode("utf-8"),
                                                    parse_constant=reject_constant))
