"""Deterministic validation. Never edits an extracted value: it only adds warnings, upgrades
verification status when independent checks agree, and builds the human-review queue."""
import datetime
import os
from decimal import Decimal

from . import config

TOL = Decimal("0.02")


def _v(f):
    """Decimal value of a numeric field or None."""
    if not f or f.get("value") is None or f.get("status") != "extracted":
        return None
    return Decimal(str(f["value"]))


def _close(a: Decimal, b: Decimal, tol=TOL):
    return abs(a - b) <= tol


def _edit1(a: str, b: str) -> bool:
    """True when strings differ by exactly one substitution/insertion/deletion."""
    if a == b:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if abs(len(a) - len(b)) == 1:
        s, l = (a, b) if len(a) < len(b) else (b, a)
        return any(l[:i] + l[i + 1:] == s for i in range(len(l)))
    return False


def _suggest(q, up, lt):
    """Never applied automatically: names the single field whose value, if misread by one character,
    would make qty x price = total consistent. For the human reviewer only."""
    digits = lambda d: str(d.quantize(Decimal("0.01")) if d % 1 else int(d)).replace(".", "").replace("-", "")
    out = []
    for field, stated, implied in (("line_total", lt, q * up), ("unit_price", up, lt / q if q else None),
                                   ("quantity", q, lt / up if up else None)):
        if implied is None or implied <= 0:
            continue
        if _edit1(digits(stated).lstrip("0") or "0", digits(implied).lstrip("0") or "0"):
            out.append({"field": field, "stated": float(stated), "would_be_consistent_if": float(implied.quantize(Decimal("0.01")))})
    return out or None


def _warn(doc, kind, message, severity="warning", **extra):
    doc["warnings"].append({"id": f"{doc['document_id']}-w{len(doc['warnings']) + 1}", "kind": kind,
                            "severity": severity, "message": message, **extra})


def _ids(*fields):
    return [f["evidence_id"] for f in fields if f and f.get("evidence_id")]


def _verify(*fields):
    for f in fields:
        if f and f.get("status") == "extracted" and f.get("confidence", 0) >= 0.8 and f["verification"] == "unverified":
            f["verification"] = "auto_verified"


def _flag(f, reason):
    if f and f.get("status") != "not_found":
        f["verification"] = "needs_review"
        f.setdefault("review_reasons", []).append(reason)


def validate_document(doc: dict):
    items = doc["invoice_items"]
    inv = doc["invoices"][0] if doc["invoices"] else None

    # 1) line arithmetic: qty x unit price - discount = line total (discount may be amount or percent)
    for it in items:
        q, up, d, lt = _v(it["quantity"]), _v(it["unit_price"]), _v(it["discount"]), _v(it["line_total"])
        if q is None or up is None or lt is None:
            continue
        gross = q * up
        cands = {"no_discount": gross}
        if d is not None:
            cands["amount_discount"] = gross - d
            cands["percent_discount"] = gross * (1 - d / 100)
        if any(_close(c, lt) for c in cands.values()):
            _verify(it["quantity"], it["unit_price"], it["line_total"])
            if d is not None:
                _verify(it["discount"])
        else:
            expected = min(cands.values(), key=lambda c: abs(c - lt))
            sugg = _suggest(q, up, lt)
            _warn(doc, "line_arithmetic_mismatch",
                  f"بند {it['id']}: الكمية×السعر={gross} لا يطابق الإجمالي {lt} / qty×price={gross} does not match line total {lt}",
                  record_id=it["id"], expected=float(expected), found=float(lt), suggestion=sugg,
                  evidence_ids=_ids(it["quantity"], it["unit_price"], it["line_total"]))
            for k in ("quantity", "unit_price", "line_total"):
                _flag(it[k], "arithmetic_mismatch")

    # 2) invoice totals
    if inv:
        sub, disc, tax, fees = (_v(inv["subtotal"]), _v(inv["discount_total"]), _v(inv["tax_total"]), _v(inv["additional_fees"]))
        tot, paid, bal = _v(inv["invoice_total"]), _v(inv["paid_total"]), _v(inv["balance_due"])
        line_sum = sum((_v(i["line_total"]) for i in items if _v(i["line_total"]) is not None), Decimal(0))
        have_lines = any(_v(i["line_total"]) is not None for i in items)
        base = sub if sub is not None else None
        gross_sum = sum((_v(i["quantity"]) * _v(i["unit_price"]) for i in items if _v(i["quantity"]) is not None and _v(i["unit_price"]) is not None), Decimal(0))
        if have_lines and base is not None:
            # a subtotal may be printed gross (before line discounts) or net; both are legitimate
            if _close(line_sum, base) or _close(gross_sum, base) or (disc is not None and _close(line_sum, base - disc)):
                _verify(inv["subtotal"])
            else:
                _warn(doc, "items_sum_vs_subtotal", f"مجموع البنود {line_sum} لا يساوي المجموع قبل الخصم {base} / "
                      f"sum of line totals {line_sum} != subtotal {base}", record_id=inv["id"], expected=float(line_sum), found=float(base),
                      evidence_ids=_ids(inv["subtotal"]))
                _flag(inv["subtotal"], "arithmetic_mismatch")
        elif have_lines and tot is not None and sub is None and disc is None and tax is None and fees is None:
            if _close(line_sum, tot):
                _verify(inv["invoice_total"])
            else:
                _warn(doc, "items_sum_vs_total", f"مجموع البنود {line_sum} لا يساوي إجمالي الفاتورة {tot} / "
                      f"sum of line totals {line_sum} != invoice total {tot}", record_id=inv["id"], expected=float(line_sum), found=float(tot),
                      evidence_ids=_ids(inv["invoice_total"]))
                _flag(inv["invoice_total"], "arithmetic_mismatch")
        if tot is not None and (sub is not None or have_lines) and (disc is not None or tax is not None or fees is not None or sub is not None):
            b = sub if sub is not None else line_sum
            expect = b - (disc or 0) + (tax or 0) + (fees or 0)
            if _close(expect, tot):
                _verify(inv["invoice_total"])
            else:
                _warn(doc, "total_formula_mismatch", f"المجموع-الخصم+الضريبة+الرسوم={expect} لا يساوي الإجمالي {tot} / "
                      f"computed {expect} != stated total {tot}", record_id=inv["id"], expected=float(expect), found=float(tot),
                      evidence_ids=_ids(inv["invoice_total"], inv["subtotal"], inv["discount_total"], inv["tax_total"]))
                _flag(inv["invoice_total"], "arithmetic_mismatch")
        if tot is not None and paid is not None and bal is not None:
            if _close(tot - paid, bal):
                _verify(inv["paid_total"], inv["balance_due"])
            else:
                _warn(doc, "balance_mismatch", f"الإجمالي-المدفوع={tot - paid} لا يساوي المتبقي {bal} / total-paid={tot - paid} != balance {bal}",
                      record_id=inv["id"], expected=float(tot - paid), found=float(bal), evidence_ids=_ids(inv["invoice_total"], inv["paid_total"], inv["balance_due"]))
                _flag(inv["balance_due"], "arithmetic_mismatch")
        if inv["invoice_date"]["status"] == "not_found":
            _warn(doc, "missing_field", "حقل غير موجود في المستند: invoice_date / field not present in document: invoice_date", "info", record_id=inv["id"], field="invoice_date")

    # Invoice row completeness is an explicit review gate. A total without any
    # auditable rows is not evidence that all charge items were captured.
    if inv and doc["document_type"] not in ("payment_receipt", "account_statement") and not items:
        _warn(doc, "invoice_rows_not_verified",
              "تعذر إثبات اكتمال بنود الفاتورة / invoice line-item completeness could not be established",
              "warning", record_id=inv["id"])
    unheaded = any(w["kind"] == "unheaded_invoice_table" for w in doc["warnings"])
    if unheaded:
        for it in items:
            for field in ("service_name", "quantity", "unit_price", "line_total"):
                _flag(it[field], "unverified_table_layout")

    # Strict opt-in financial completeness review for OCR-benchmark candidate.
    # Never fills in or silently calculates missing prices/quantities.
    if os.environ.get("MDIA_STRICT_INVOICE_REVIEW", "0") == "1" and inv:
        incomplete = []
        for it in items:
            missing = [k for k in ("service_name", "quantity", "unit_price", "line_total")
                       if it[k]["status"] != "extracted" or it[k].get("value") is None]
            if not missing:
                continue
            incomplete.append(it["id"])
            _warn(doc, "incomplete_invoice_item",
                  f"بيانات مالية ناقصة في بند {it['id']}: {', '.join(missing)} / invoice item missing evidence-backed values",
                  "warning", record_id=it["id"], missing_fields=missing,
                  evidence_ids=_ids(*(it[k] for k in ("service_name", "quantity", "unit_price", "line_total"))))
            for key in ("service_name", "quantity", "unit_price", "line_total"):
                if key in missing:
                    _flag(it[key], "incomplete_invoice_item")
        if incomplete:
            _flag(inv["invoice_total"], "incomplete_invoice_items")
            _warn(doc, "invoice_total_needs_completeness_review",
                  "الإجمالي لا يثبت اكتمال بنود الفاتورة / reported total cannot prove missing items are complete",
                  "warning", record_id=inv["id"], incomplete_item_ids=incomplete,
                  evidence_ids=_ids(inv["invoice_total"]))

    # 3) probable duplicates (kept, only flagged: repetition is not proof of double billing)
    seen = {}
    for it in items:
        key = (it["service_name"]["raw"], it["quantity"]["raw"], it["unit_price"]["raw"], it["line_total"]["raw"], it["service_date"]["raw"])
        if key[0] is None:
            continue
        if key in seen:
            _warn(doc, "possible_duplicate_line", f"بند مكرر محتمل: {key[0]} (يُراجع يدويًا؛ لم يُحذف) / possible duplicate line (kept)",
                  "info", record_ids=[seen[key], it["id"]])
        else:
            seen[key] = it["id"]

    # 4) hospital stay
    h = doc["hospitalization"]
    if h:
        a, d, n = h.get("admission_date"), h.get("discharge_date"), _v(h.get("length_of_stay_days"))
        if a and d and a.get("value") and d.get("value"):
            da, dd = datetime.date.fromisoformat(a["value"]), datetime.date.fromisoformat(d["value"])
            if dd < da:
                _warn(doc, "discharge_before_admission", "تاريخ الخروج قبل الدخول / discharge date precedes admission", "error",
                      evidence_ids=_ids(a, d))
                _flag(a, "date_conflict")
                _flag(d, "date_conflict")
            elif n is not None and int(n) not in ((dd - da).days, (dd - da).days + 1):
                _warn(doc, "stay_days_mismatch", f"عدد الأيام {int(n)} لا يطابق الفرق بين التاريخين ({(dd - da).days}) / stay days mismatch",
                      evidence_ids=_ids(a, d, h.get("length_of_stay_days")))
                _flag(h["length_of_stay_days"], "date_conflict")

    # 5) clinical sanity: a diagnosis must be printed, never derived
    for dx in doc["diagnoses"]:
        if dx["text"]["status"] == "not_found":
            _warn(doc, "empty_diagnosis", "سجل تشخيص بلا نص", "error", record_id=dx["id"])

    # 6) review queue
    queue = []

    def scan(rec_id, rec):
        for k, f in rec.items():
            if isinstance(f, dict) and "verification" in f and f.get("status") != "not_found":
                if f["verification"] == "needs_review":
                    queue.append({"record_id": rec_id, "field": k, "raw": f["raw"], "evidence_id": f["evidence_id"],
                                  "page": f["page"], "confidence": f["confidence"],
                                  "reasons": f.get("review_reasons") or (["low_confidence"] if f["confidence"] < config.LOW_CONF else ["needs_review"])})
    did = doc["document_id"]
    scan(f"{did}:patient", doc["patient"])
    scan(f"{did}:provider", doc["provider"])
    scan(f"{did}:hospitalization", doc["hospitalization"])
    for key in ("invoices", "invoice_items", "medications", "diagnoses", "laboratory_tests", "imaging", "procedures"):
        for rec in doc[key]:
            scan(rec["id"], rec)
    # required fields that are simply not printed (or not readable) must be seen by a human
    def need(rec_id, key, f, page=None):
        if f is None or f.get("status") == "not_found":
            queue.append({"record_id": rec_id, "field": key, "raw": None, "evidence_id": None, "page": page,
                          "confidence": 0.0, "reasons": ["required_field_not_found"]})
            _warn(doc, "missing_field", f"حقل مطلوب غير موجود: {key} / required field not found: {key}", "info", record_id=rec_id, field=key)
    if doc["document_type"] != "unknown" and doc["patient"]:
        need(f"{did}:patient", "name", doc["patient"].get("name"))
    if inv:
        need(inv["id"], "invoice_number", inv["invoice_number"])
        need(inv["id"], "invoice_total", inv["invoice_total"])
        if not items and doc["document_type"] not in ("payment_receipt", "account_statement"):
            queue.append({"record_id": inv["id"], "field": "invoice_items", "raw": None,
                          "evidence_id": None, "page": doc["pages"][0] if doc["pages"] else None,
                          "confidence": 0.0, "reasons": ["invoice_rows_not_verified"]})
    doc["requires_human_review"] = queue
    if any(w["severity"] == "error" for w in doc["warnings"]) or queue:
        doc["processing_status"] = "completed_with_review"
    return doc
