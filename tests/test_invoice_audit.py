"""Synthetic tests of the evidence-first, three-way audit core."""
import copy
import unittest

from invoice_audit import audit, MATCH, EXCEPTION, UNVERIFIABLE

HASH = "a" * 64


def field(value, status="verified"):
    return {"value": value, "verification": status, "evidence_id": "e-1",
            "source_hash": HASH, "source_locator": "page:1:row:1"}


def doc(kind, qty="10", price="5", total=None):
    line = {"sku": field("SKU-1"), "unit": field("pcs"),
            "quantity": field(qty)}
    if kind != "grn":
        line["unit_price"] = field(price)
    if kind == "invoice":
        line["line_total"] = field(total or str(int(qty) * int(price)))
    item = {"kind": kind, "document_id": field(kind + "-1"),
            "supplier_id": field("supplier-1"), "currency": field("USD"),
            "requires_human_review": False, "lines": [line]}
    if kind == "invoice":
        item["stated_total"] = field(total or str(int(qty) * int(price)))
        item["has_other_charges"] = False
        item["single_invoice_scope"] = True
    if kind == "po":
        item["single_po_scope"] = True
    if kind == "grn":
        item["complete_receipt_scope"] = True
    return item


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.po, self.grn, self.inv = doc("po"), doc("grn"), doc("invoice")

    def check(self, expected):
        result = audit(self.po, self.grn, self.inv)
        self.assertEqual(expected, result["status"], result)
        self.assertIs(result["approval"], False)
        return result

    def test_exact_match_no_payment_approval(self):
        self.check(MATCH)

    def test_quantity_exceeds_receipt(self):
        self.grn["lines"][0]["quantity"]["value"] = "9"
        findings = self.check(EXCEPTION)["findings"]
        self.assertIn("QTY_OVER_RECEIVED", {f["rule"] for f in findings})

    def test_quantity_exceeds_order(self):
        self.inv["lines"][0]["quantity"]["value"] = "11"
        self.inv["lines"][0]["line_total"]["value"] = "55"
        self.inv["stated_total"]["value"] = "55"
        findings = self.check(EXCEPTION)["findings"]
        self.assertIn("QTY_OVER_ORDERED", {f["rule"] for f in findings})

    def test_unit_price_difference(self):
        self.inv["lines"][0]["unit_price"]["value"] = "6"
        self.inv["lines"][0]["line_total"]["value"] = "60"
        self.inv["stated_total"]["value"] = "60"
        self.assertIn("UNIT_PRICE_DIFFERENCE",
                      {f["rule"] for f in self.check(EXCEPTION)["findings"]})

    def test_stated_total_difference(self):
        self.inv["stated_total"]["value"] = "51"
        self.assertIn("INVOICE_TOTAL_DIFFERENCE",
                      {f["rule"] for f in self.check(EXCEPTION)["findings"]})

    def test_line_calculation_difference(self):
        self.inv["lines"][0]["line_total"]["value"] = "55"
        self.inv["stated_total"]["value"] = "55"
        self.assertIn("LINE_TOTAL_DIFFERENCE",
                      {f["rule"] for f in self.check(EXCEPTION)["findings"]})

    def test_missing_evidence(self):
        self.inv["lines"][0]["quantity"]["evidence_id"] = None
        self.check(UNVERIFIABLE)

    def test_ocr_provisional_not_verified(self):
        self.inv["lines"][0]["quantity"]["verification"] = "provisional"
        self.check(UNVERIFIABLE)

    def test_float_rejected(self):
        self.inv["lines"][0]["quantity"]["value"] = 10.0
        self.check(UNVERIFIABLE)

    def test_empty_original_hash_rejected(self):
        self.po["lines"][0]["unit_price"]["source_hash"] = ""
        self.check(UNVERIFIABLE)

    def test_currency_mismatch(self):
        self.inv["currency"]["value"] = "SAR"
        self.check(UNVERIFIABLE)

    def test_supplier_mismatch(self):
        self.inv["supplier_id"]["value"] = "unknown"
        self.check(UNVERIFIABLE)

    def test_unknown_item(self):
        self.inv["lines"][0]["sku"]["value"] = "other"
        self.check(UNVERIFIABLE)

    def test_missing_receipt_item(self):
        self.grn["lines"][0]["sku"]["value"] = "other"
        self.check(UNVERIFIABLE)

    def test_duplicate_line_requires_allocation(self):
        self.inv["lines"].append(copy.deepcopy(self.inv["lines"][0]))
        self.check(UNVERIFIABLE)

    def test_requires_review_cannot_match(self):
        self.po["requires_human_review"] = True
        self.check(UNVERIFIABLE)

    def test_charge_scope_fail_closed(self):
        del self.inv["has_other_charges"]
        self.check(UNVERIFIABLE)

    def test_multi_document_scope_fail_closed(self):
        self.grn["complete_receipt_scope"] = False
        self.check(UNVERIFIABLE)

    def test_negative_price_rejected(self):
        self.po["lines"][0]["unit_price"]["value"] = "-5"
        self.check(UNVERIFIABLE)

    def test_non_finite_numeric_rejected(self):
        self.inv["lines"][0]["quantity"]["value"] = "NaN"
        self.check(UNVERIFIABLE)

    def test_zero_quantity_rejected(self):
        self.grn["lines"][0]["quantity"]["value"] = "0"
        self.check(UNVERIFIABLE)

    def test_under_received_quantity_in_full_scope(self):
        self.inv["lines"][0]["quantity"]["value"] = "9"
        self.inv["lines"][0]["line_total"]["value"] = "45"
        self.inv["stated_total"]["value"] = "45"
        self.assertIn("QTY_UNDER_RECEIVED",
                      {f["rule"] for f in self.check(EXCEPTION)["findings"]})

    def test_received_item_not_in_invoiced_lines(self):
        second = copy.deepcopy(self.grn["lines"][0])
        second["sku"]["value"] = "SKU-2"
        self.grn["lines"].append(second)
        self.check(UNVERIFIABLE)

    def test_no_rounded_float(self):
        self.po["lines"][0]["unit_price"]["value"] = "0.10"
        self.inv["lines"][0]["unit_price"]["value"] = "0.10"
        self.inv["lines"][0]["line_total"]["value"] = "1.00"
        self.inv["stated_total"]["value"] = "1.00"
        self.check(MATCH)


if __name__ == "__main__":
    unittest.main()
