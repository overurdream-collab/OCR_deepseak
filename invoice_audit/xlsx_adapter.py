"""Strict first-party Excel template adapter: no OCR, no formula execution.

Rejects arbitrary vendor spreadsheets until a reviewed field mapping exists.
This adapter assures exact extraction of original workbook cell values, NOT
genuine supplier/warehouse identity or commercial facts.
"""
from __future__ import annotations

import hashlib
from io import BytesIO

from .core import UNVERIFIABLE, audit

LABELS = {
    1: "kind", 2: "document_id", 3: "supplier_id", 4: "currency",
    5: "po_reference", 6: "grn_reference", 7: "stated_total",
    8: "has_other_charges", 9: "single_invoice_scope",
    10: "single_po_scope", 11: "complete_receipt_scope",
}
HEADERS = ("sku", "unit", "quantity", "unit_price", "line_total")
TYPES = ("po", "grn", "invoice")


def _unverifiable(reason):
    return {"status": UNVERIFIABLE, "approval": False, "findings": [],
            "reasons": [reason], "source_authenticity": "not_authenticated",
            "ruleset": "invoice-audit-v0.1"}


def _wrap(value, digest, location):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{location}: empty or non-text field")
    return {"value": value, "verification": "verified",
            "evidence_id": f"{digest}:{location}", "source_hash": digest,
            "source_locator": f"xlsx:{location}"}


def parse_xlsx_template(raw: bytes, expected_kind: str) -> dict:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise ValueError("openpyxl is required") from exc
    if expected_kind not in TYPES or not isinstance(raw, bytes) or not raw or len(raw) > 5_000_000:
        raise ValueError("invalid Excel source")
    try:
        wb = load_workbook(BytesIO(raw), read_only=True, data_only=False, keep_links=False)
    except Exception as exc:
        raise ValueError("invalid XLSX workbook") from exc
    try:
        if wb.sheetnames != ["Audit"]:
            raise ValueError("expected exactly one named Audit worksheet")
        ws = wb["Audit"]
        if ws.max_row > 1012 or ws.max_column > 5:
            raise ValueError("unsupported workbook dimensions")
        # Scan every cell for unsupported formulas, extra values and non-plain types.
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type == "f":
                    raise ValueError("formula cells are unsupported")
                if cell.data_type == "e":
                    raise ValueError("error cells are unsupported")
                if cell.value is None:
                    continue
                if cell.row <= 11:
                    if cell.column > 2:
                        raise ValueError("unexpected header cell")
                    if cell.column == 1 and cell.row <= 11 and cell.value != LABELS[cell.row]:
                        raise ValueError(f"{cell.coordinate}: bad template label")
                elif cell.column > 5:
                    raise ValueError("unexpected line value")
        if tuple(ws.cell(12, col).value for col in range(1, 6)) != HEADERS:
            raise ValueError("row 12 column headers do not match")
        hdr = {LABELS[row]: ws.cell(row, 2).value for row in range(1, 12)}
        if hdr["kind"] != expected_kind:
            raise ValueError("document kind mismatch")
        digest = hashlib.sha256(raw).hexdigest()
        doc = {"kind": expected_kind, "requires_human_review": False}
        for key, row in (("document_id", 2), ("supplier_id", 3), ("currency", 4)):
            doc[key] = _wrap(hdr[key], digest, f"B{row}")
        if expected_kind in ("grn", "invoice"):
            doc["po_reference"] = _wrap(hdr["po_reference"], digest, "B5")
        if expected_kind == "invoice":
            doc["grn_reference"] = _wrap(hdr["grn_reference"], digest, "B6")
            doc["stated_total"] = _wrap(hdr["stated_total"], digest, "B7")
        controls = {"po": ["single_po_scope"],
                    "grn": ["complete_receipt_scope"],
                    "invoice": ["has_other_charges", "single_invoice_scope"]}
        for key in controls[expected_kind]:
            if type(hdr[key]) is not bool:
                raise ValueError(f"{key} must be true/false (boolean cell)")
            doc[key] = hdr[key]
        allowed = {"po": {"kind", "document_id", "supplier_id", "currency", "single_po_scope"},
                   "grn": {"kind", "document_id", "supplier_id", "currency",
                           "po_reference", "complete_receipt_scope"},
                   "invoice": {"kind", "document_id", "supplier_id", "currency",
                               "po_reference", "grn_reference", "stated_total",
                               "has_other_charges", "single_invoice_scope"}}
        for key, value in hdr.items():
            if key not in allowed[expected_kind] and value is not None:
                raise ValueError(f"unsupported header field {key}")
        doc["lines"] = []
        for row in range(13, ws.max_row + 1):
            vals = [ws.cell(row, col).value for col in range(1, 6)]
            if all(value is None for value in vals):
                continue
            keys = {"po": HEADERS[:4], "grn": HEADERS[:3], "invoice": HEADERS}[expected_kind]
            if any(value is not None for value in vals[len(keys):]):
                raise ValueError(f"unexpected line data at row {row}")
            entry = {key: _wrap(vals[index], digest, f"{'ABCDE'[index]}{row}")
                     for index, key in enumerate(keys)}
            doc["lines"].append(entry)
        if not doc["lines"]:
            raise ValueError("no invoice/PO/GRN lines")
        return doc
    finally:
        wb.close()


def audit_xlsx_templates(po: bytes, grn: bytes, invoice: bytes) -> dict:
    try:
        docs = [parse_xlsx_template(data, kind) for data, kind in zip(
            (po, grn, invoice), TYPES)]
    except ValueError as exc:
        return _unverifiable(str(exc))
    report = audit(*docs)
    report["sources"] = {kind + "_sha256": hashlib.sha256(data).hexdigest()
                         for kind, data in zip(TYPES, (po, grn, invoice))}
    report["source_authenticity"] = "not_authenticated"
    return report
