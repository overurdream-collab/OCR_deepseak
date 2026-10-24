"""Synthetic geometry audit regressions; no Paddle download or real medical data."""
import tempfile
import unittest
from pathlib import Path

from scripts.audit_arabic_geometry import BASELINES, H, TOLERANCE_PT, check_geometry, fixtures


def fake(value, band, delta=0, page=1, evidence_page=1):
    y = (BASELINES[band] + delta) / H
    field = {"value": value, "evidence_id": "e1", "page": page}
    evidence = {"id": "e1", "bbox": [0.4, y-0.005, 0.6, y+0.005],
                "page": evidence_page, "text": str(value)}
    return field, evidence


class ArabicRowGeometryTests(unittest.TestCase):
    def test_matching_field_in_expected_source_row(self):
        field, ev = fake("خالد يوسف", "patient_invoice", 3)
        r = check_geometry(field, ev, "patient_invoice", "خالد يوسف", "patient.name")
        self.assertTrue(r["row_band_consistent"])
        self.assertEqual(r["row_y_offset_pt"], 3)

    def test_reject_neighbouring_invoice_row(self):
        field, ev = fake("كشف استشاري", "item1", 15)
        result = check_geometry(field, ev, "item1", "كشف استشاري", "items.1.name")
        self.assertTrue(result["value_match"])
        self.assertFalse(result["row_band_consistent"])

    def test_reject_correct_value_on_wrong_row(self):
        field, ev = fake("خالد يوسف", "patient_invoice", 45)
        r = check_geometry(field, ev, "patient_invoice", "خالد يوسف", "patient.name")
        self.assertTrue(r["value_match"])
        self.assertFalse(r["row_band_consistent"])
        self.assertGreater(abs(r["row_y_offset_pt"]), TOLERANCE_PT)

    def test_missing_or_invalid_evidence_not_accepted(self):
        field, ev = fake("INV-4004", "invoice_no")
        ev["bbox"] = [0.8, 0.2, 0.1, 0.3]
        self.assertFalse(check_geometry(field, ev, "invoice_no", "INV-4004", "invoice.number")["geometry_valid"])
        self.assertFalse(check_geometry(field, None, "invoice_no", "INV-4004", "invoice.number")["row_band_consistent"])

    def test_reject_evidence_from_another_page(self):
        field, ev = fake("خالد يوسف", "patient_invoice", evidence_page=2)
        self.assertFalse(check_geometry(field, ev, "patient_invoice", "خالد يوسف", "patient.name")["geometry_valid"])

    def test_corrupt_invoice_number_not_saved_by_correct_geometry(self):
        field, ev = fake("V-44", "invoice_no")
        result = check_geometry(field, ev, "invoice_no", "INV-4004", "invoice.number")
        self.assertTrue(result["geometry_valid"])
        self.assertFalse(result["row_band_consistent"])

    def test_six_synthetic_pdf_variants(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            names = fixtures(root)
            self.assertEqual(len(names), 6)
            self.assertIn("invoice_eastern.pdf", names)
            self.assertIn("prescription_logical.pdf", names)
            self.assertTrue(all((root/n).read_bytes().startswith(b"%PDF") for n in names))


if __name__ == "__main__":
    unittest.main()
