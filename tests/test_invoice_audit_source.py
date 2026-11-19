"""Content-bound input acceptance and negative controls."""
import json
import unittest

from invoice_audit import audit_json_sources, parse_structured_json, MATCH, EXCEPTION, UNVERIFIABLE


def payload(kind, quantity="10", price="5"):
    row = {"sku": "A1", "unit": "pcs", "quantity": quantity}
    if kind != "grn":
        row["unit_price"] = price
    if kind == "invoice":
        row["line_total"] = "50"
    doc = {"kind": kind, "document_id": kind + "-1",
           "supplier_id": "s1", "currency": "USD", "lines": [row]}
    if kind == "po":
        doc["single_po_scope"] = True
    if kind == "grn":
        doc["po_reference"] = "po-1"
        doc["complete_receipt_scope"] = True
    if kind == "invoice":
        doc["po_reference"] = "po-1"
        doc["grn_reference"] = "grn-1"
        doc.update(stated_total="50", has_other_charges=False, single_invoice_scope=True)
    return doc


def blob(d):
    return json.dumps(d, ensure_ascii=False).encode("utf-8")


class StructuredSourcesTests(unittest.TestCase):
    def setUp(self):
        self.po = payload("po")
        self.grn = payload("grn")
        self.invoice = payload("invoice")

    def check(self, expected):
        result = audit_json_sources(blob(self.po), blob(self.grn), blob(self.invoice))
        self.assertEqual(result["status"], expected, result)
        self.assertIs(result["approval"], False)
        return result

    def test_content_bound_match(self):
        result = self.check(MATCH)
        self.assertEqual(result["source_authenticity"], "not_authenticated")
        self.assertEqual(len(result["sources"]["invoice_sha256"]), 64)

    def test_raw_field_change_exposes_difference(self):
        self.invoice["lines"][0]["unit_price"] = "6"
        self.assertIn("UNIT_PRICE_DIFFERENCE",
                      {f["rule"] for f in self.check(EXCEPTION)["findings"]})

    def test_raw_bad_arithmetic(self):
        self.invoice["lines"][0]["line_total"] = "51"
        self.assertIn("LINE_TOTAL_DIFFERENCE",
                      {f["rule"] for f in self.check(EXCEPTION)["findings"]})

    def test_json_duplicate_key_rejected(self):
        duplicated = b'{"kind":"po","kind":"po"}'
        with self.assertRaises(ValueError):
            parse_structured_json(duplicated, "po")

    def test_json_number_float_rejected(self):
        original = blob(self.invoice).replace(b'"quantity": "10"', b'"quantity": 10.0')
        result = audit_json_sources(blob(self.po), blob(self.grn), original)
        self.assertEqual(result["status"], UNVERIFIABLE)

    def test_unknown_tax_field_rejected(self):
        self.invoice["tax"] = "99.00"
        self.check(UNVERIFIABLE)

    def test_unknown_line_tax_rejected(self):
        self.invoice["lines"][0]["tax"] = "99.00"
        self.check(UNVERIFIABLE)

    def test_missing_charges_declaration(self):
        del self.invoice["has_other_charges"]
        self.check(UNVERIFIABLE)

    def test_unverified_source_structure(self):
        self.po["lines"][0]["quantity"] = ""
        self.check(UNVERIFIABLE)

    def test_unsupported_scope_rejected(self):
        self.invoice["single_invoice_scope"] = False
        self.check(UNVERIFIABLE)

    def test_wrong_document_kind(self):
        self.invoice["kind"] = "po"
        self.check(UNVERIFIABLE)

    def test_unrelated_po_reference_rejected(self):
        self.invoice["po_reference"] = "po-other"
        self.check(UNVERIFIABLE)

    def test_unrelated_receipt_reference_rejected(self):
        self.invoice["grn_reference"] = "grn-other"
        self.check(UNVERIFIABLE)

    def test_hash_binds_source_content(self):
        p1 = parse_structured_json(blob(self.po), "po")
        self.po["lines"][0]["quantity"] = "11"
        p2 = parse_structured_json(blob(self.po), "po")
        self.assertNotEqual(p1["lines"][0]["quantity"]["source_hash"],
                            p2["lines"][0]["quantity"]["source_hash"])


if __name__ == "__main__":
    unittest.main()
