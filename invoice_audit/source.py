"""Content-bound JSON source adapter for deterministic audit prototyping.

Authenticates field transcription against raw uploaded bytes; does NOT
authenticate the issuer or physical delivery. Keep raw bytes in secured storage.
"""
from __future__ import annotations

import hashlib
import json
from .core import UNVERIFIABLE, audit


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_number(_):
    raise ValueError("JSON numeric literal forbidden: use decimal strings")


def _pointer(*parts):
    return "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def _wrap(value, digest, *parts):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{_pointer(*parts)}: expected nonempty string")
    path = _pointer(*parts)
    return {"value": value, "verification": "verified",
            "evidence_id": f"{digest}:{path}",
            "source_hash": digest, "source_locator": f"json_pointer:{path}"}


def parse_structured_json(raw: bytes, expected_kind: str) -> dict:
    """Extract string values from ORIGINAL JSON bytes, not supplied OCR claims."""
    if not isinstance(raw, bytes) or len(raw) > 2_000_000 or not raw:
        raise ValueError("source must be non-empty JSON bytes <= 2 MB")
    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                         parse_float=_reject_number, parse_int=_reject_number,
                         parse_constant=_reject_number)
    except (UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError("invalid UTF-8 JSON") from exc
    if not isinstance(doc, dict) or doc.get("kind") != expected_kind:
        raise ValueError("wrong document kind")
    allowed = {"kind", "document_id", "supplier_id", "currency", "lines"}
    if expected_kind == "invoice":
        allowed |= {"stated_total", "has_other_charges", "single_invoice_scope"}
    elif expected_kind == "po":
        allowed.add("single_po_scope")
    else:
        allowed.add("complete_receipt_scope")
    if set(doc) - allowed:
        raise ValueError("unsupported top-level fields; cannot silently ignore")
    digest = hashlib.sha256(raw).hexdigest()
    output = {"kind": expected_kind, "requires_human_review": False}
    for key in ("document_id", "supplier_id", "currency"):
        output[key] = _wrap(doc.get(key), digest, key)
    lines = doc.get("lines")
    if not isinstance(lines, list) or not 0 < len(lines) <= 1000:
        raise ValueError("must have 1 to 1000 lines")
    output["lines"] = []
    for index, line in enumerate(lines):
        if not isinstance(line, dict):
            raise ValueError("line must be an object")
        row = {}
        keys = ["sku", "unit", "quantity"]
        if expected_kind != "grn":
            keys.append("unit_price")
        if expected_kind == "invoice":
            keys.append("line_total")
        if set(line) - set(keys):
            raise ValueError("unsupported line fields; cannot silently ignore")
        for key in keys:
            row[key] = _wrap(line.get(key), digest, "lines", index, key)
        output["lines"].append(row)
    if expected_kind == "invoice":
        output["stated_total"] = _wrap(doc.get("stated_total"), digest, "stated_total")
        if type(doc.get("has_other_charges")) is not bool or type(doc.get("single_invoice_scope")) is not bool:
            raise ValueError("invoice scope flags must be explicit boolean")
        output["has_other_charges"] = doc["has_other_charges"]
        output["single_invoice_scope"] = doc["single_invoice_scope"]
    elif expected_kind == "po":
        if type(doc.get("single_po_scope")) is not bool:
            raise ValueError("single_po_scope must be explicit boolean")
        output["single_po_scope"] = doc["single_po_scope"]
    else:
        if type(doc.get("complete_receipt_scope")) is not bool:
            raise ValueError("complete_receipt_scope must be explicit boolean")
        output["complete_receipt_scope"] = doc["complete_receipt_scope"]
    return output


def audit_json_sources(po_bytes: bytes, grn_bytes: bytes, invoice_bytes: bytes) -> dict:
    """Audits faithful JSON field values, not source authenticity.

    NEVER use this as authorization to pay; an issuer could submit false data.
    """
    try:
        po = parse_structured_json(po_bytes, "po")
        grn = parse_structured_json(grn_bytes, "grn")
        invoice = parse_structured_json(invoice_bytes, "invoice")
    except ValueError as exc:
        return {"status": UNVERIFIABLE, "approval": False, "findings": [],
                "reasons": [str(exc)], "ruleset": "invoice-audit-v0.1"}
    result = audit(po, grn, invoice)
    result["sources"] = {"po_sha256": hashlib.sha256(po_bytes).hexdigest(),
                         "grn_sha256": hashlib.sha256(grn_bytes).hexdigest(),
                         "invoice_sha256": hashlib.sha256(invoice_bytes).hexdigest()}
    result["source_authenticity"] = "not_authenticated"
    return result
