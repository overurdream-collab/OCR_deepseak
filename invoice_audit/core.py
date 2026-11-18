"""Evidence-first, deterministic, fail-closed three-way invoice audit.

This module does NOT perform OCR and never authorizes payment. All input
numbers are strings; sources must be independently verified before matching.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any

MATCH = "VERIFIED_MATCH"
EXCEPTION = "VERIFIED_EXCEPTION"
UNVERIFIABLE = "UNVERIFIABLE"
CRITICAL = ("supplier_id", "currency", "document_id", "lines")


def _decimal(value: Any, field: str) -> Decimal:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{field}: must be a canonical decimal string (not float)")
    if len(value) > 32 or not re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\\.[0-9]{1,6})?", value):
        raise ValueError(f"{field}: unsupported decimal precision or notation")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{field}: invalid decimal") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field}: non-finite decimal")
    return parsed


def _evidence_ok(field: dict) -> bool:
    if not isinstance(field, dict):
        return False
    return (
        field.get("verification") == "verified"
        and isinstance(field.get("evidence_id"), str)
        and bool(field["evidence_id"].strip())
        and isinstance(field.get("source_hash"), str)
        and len(field["source_hash"]) == 64
        and all(c in "0123456789abcdef" for c in field["source_hash"])
        and isinstance(field.get("source_locator"), str)
        and bool(field["source_locator"].strip())
        and field.get("value") is not None
    )


def _value(record: dict, key: str, errors: list, context: str) -> Any:
    field = record.get(key)
    if not _evidence_ok(field):
        errors.append(f"{context}.{key}: missing independently verified evidence")
        return None
    return field["value"]


def _number(record: dict, key: str, errors: list, context: str) -> Decimal | None:
    raw = _value(record, key, errors, context)
    if raw is None:
        return None
    try:
        return _decimal(raw, f"{context}.{key}")
    except ValueError as exc:
        errors.append(str(exc))
        return None


def _text(record: dict, key: str, errors: list, context: str) -> str | None:
    raw = _value(record, key, errors, context)
    if not isinstance(raw, str) or not raw.strip() or raw != raw.strip():
        errors.append(f"{context}.{key}: invalid string")
        return None
    return raw


def _parse(document: Any, kind: str, errors: list) -> dict | None:
    if not isinstance(document, dict) or document.get("kind") != kind:
        errors.append(f"{kind}: missing or invalid document")
        return None
    if document.get("requires_human_review", True) is not False:
        errors.append(f"{kind}: pending human review")
    fields = {k: _text(document, k, errors, kind) for k in
              ("document_id", "supplier_id", "currency")}
    if fields["currency"] not in ("USD", "SAR", "YER"):
        errors.append(f"{kind}: unsupported or ambiguous currency")
    lines = document.get("lines")
    if not isinstance(lines, list) or not lines:
        errors.append(f"{kind}: no lines")
        return None
    parsed = {}
    for i, line in enumerate(lines):
        ctx = f"{kind}.lines[{i}]"
        if not isinstance(line, dict):
            errors.append(f"{ctx}: invalid line")
            continue
        sku = _text(line, "sku", errors, ctx)
        unit = _text(line, "unit", errors, ctx)
        quantity = _number(line, "quantity", errors, ctx)
        price = _number(line, "unit_price", errors, ctx) if kind != "grn" else None
        total = _number(line, "line_total", errors, ctx) if kind == "invoice" else None
        if quantity is not None and quantity <= 0:
            errors.append(f"{ctx}: quantity must be positive")
        if price is not None and price < 0:
            errors.append(f"{ctx}: negative unit price")
        if total is not None and total < 0:
            errors.append(f"{ctx}: negative line total")
        if not sku or not unit:
            continue
        key = (sku, unit)
        if key in parsed:
            errors.append(f"{ctx}: duplicate sku+unit; explicit allocation required")
            continue
        parsed[key] = {"sku": sku, "unit": unit, "quantity": quantity,
                       "unit_price": price, "line_total": total}
    if kind in ("grn", "invoice"):
        fields["po_reference"] = _text(document, "po_reference", errors, kind)
    if kind == "invoice":
        fields["grn_reference"] = _text(document, "grn_reference", errors, kind)
    fields["lines"] = parsed
    if kind == "invoice":
        fields["stated_total"] = _number(document, "stated_total", errors, kind)
    return fields


def audit(po: dict, grn: dict, invoice: dict) -> dict:
    """Return a finding report, NEVER a payment approval.

    A document must be independently verified before this method may call
    its numbers VERIFIED. OCR confidence alone must NOT set verification.
    """
    errors = []
    docs = [_parse(po, "po", errors), _parse(grn, "grn", errors),
            _parse(invoice, "invoice", errors)]
    if errors or any(x is None for x in docs):
        return {"status": UNVERIFIABLE, "approval": False,
                "findings": [], "reasons": sorted(set(errors)),
                "ruleset": "invoice-audit-v0.1"}
    order, receipt, bill = docs
    if receipt["po_reference"] != order["document_id"] or bill["po_reference"] != order["document_id"]:
        errors.append("purchase order reference mismatch")
    if bill["grn_reference"] != receipt["document_id"]:
        errors.append("goods receipt reference mismatch")
    if len({order["supplier_id"], receipt["supplier_id"], bill["supplier_id"]}) != 1:
        errors.append("supplier identity mismatch")
    if len({order["currency"], receipt["currency"], bill["currency"]}) != 1:
        errors.append("currency mismatch")
    for doc_kind, doc in (("grn", receipt), ("invoice", bill)):
        extra = set(doc["lines"]) - set(order["lines"])
        if extra:
            errors.append(f"{doc_kind}: item not in purchase order: {sorted(extra)}")
    if errors:
        return {"status": UNVERIFIABLE, "approval": False,
                "findings": [], "reasons": sorted(set(errors)),
                "ruleset": "invoice-audit-v0.1"}
    findings = []
    for key in sorted(set(order["lines"]) - set(receipt["lines"])):
        findings.append({"rule": "ORDERED_NOT_RECEIVED", "sku": key[0],
                         "message": "ordered item absent from receipt in declared complete scope"})
    for key in sorted(set(order["lines"]) - set(bill["lines"])):
        findings.append({"rule": "ORDERED_NOT_INVOICED", "sku": key[0],
                         "message": "ordered item absent from invoice in declared full scope"})
    calculated_total = Decimal("0")
    for key in sorted(set(receipt["lines"]) - set(bill["lines"])):
        findings.append({"rule": "RECEIVED_NOT_INVOICED", "sku": key[0],
                         "message": "received item absent from invoice in declared full scope"})
    for key, line in sorted(bill["lines"].items()):
        ordered = order["lines"][key]
        received = receipt["lines"].get(key)
        if received is None:
            findings.append({"rule": "NOT_RECEIVED", "sku": line["sku"],
                             "message": "invoice item absent from receipt"})
            continue
        qty, poqty, receivedqty = line["quantity"], ordered["quantity"], received["quantity"]
        if qty != receivedqty:
            findings.append({"rule": "QTY_OVER_RECEIVED" if qty > receivedqty
                             else "QTY_UNDER_RECEIVED", "sku": line["sku"],
                             "difference": str(qty - receivedqty)})
        if qty > poqty:
            findings.append({"rule": "QTY_OVER_ORDERED", "sku": line["sku"],
                             "difference": str(qty - poqty)})
        if line["unit_price"] != ordered["unit_price"]:
            findings.append({"rule": "UNIT_PRICE_DIFFERENCE", "sku": line["sku"],
                             "difference": str(line["unit_price"] - ordered["unit_price"])})
        calculated = qty * line["unit_price"]
        if calculated != line["line_total"]:
            findings.append({"rule": "LINE_TOTAL_DIFFERENCE", "sku": line["sku"],
                             "difference": str(line["line_total"] - calculated)})
        calculated_total += line["line_total"]
    if calculated_total != bill["stated_total"]:
        findings.append({"rule": "INVOICE_TOTAL_DIFFERENCE", "sku": None,
                         "difference": str(bill["stated_total"] - calculated_total)})
    # Other taxes, shipping, discounts, partial invoices, previous receipts or
    # allocations require explicit approved rules before a MATCH is possible.
    if invoice.get("has_other_charges") is not False:
        return {"status": UNVERIFIABLE, "approval": False, "findings": findings,
                "reasons": ["charges/tax/discount scope not independently verified"],
                "ruleset": "invoice-audit-v0.1"}
    if not (po.get("single_po_scope") is True and grn.get("complete_receipt_scope") is True
            and invoice.get("single_invoice_scope") is True):
        return {"status": UNVERIFIABLE, "approval": False, "findings": findings,
                "reasons": ["multi-document or allocation scope not verified"],
                "ruleset": "invoice-audit-v0.1"}
    return {"status": EXCEPTION if findings else MATCH, "approval": False,
            "findings": findings, "reasons": [], "ruleset": "invoice-audit-v0.1"}
