"""OCR whitespace fixes cannot invent or change medical information."""
import copy
import unittest
from mdia.service_spacing import repair_service_spacing, repair_document_service_names


class SourcePreservingSpacingTests(unittest.TestCase):
    def test_actual_ocr_joined_service_names(self):
        for raw, corrected in (
            ("CreatinineTest", "Creatinine Test"),
            ("تخطيطقلب", "تخطيط قلب"),
            ("تحليل دمشامل", "تحليل دم شامل"),
            ("تح ليل سكر صائم", "تحليل سكر صائم"),
            ("تحليل وظائ ف الكلی", "تحليل وظائف الكلی"),
        ):
            with self.subTest(raw=raw):
                actual = repair_service_spacing(raw)
                self.assertEqual(actual, corrected)
                self.assertEqual(actual.replace(" ", ""), raw.replace(" ", ""))

    def test_no_medical_or_sensitive_character_change(self):
        for text in (
            "كلى", "كلي", "ليلى حسن", "ليلی حسن", "أقراص باراسيتامول",
            "دمشاملكبد", "INV-710114", "No:INV-710114",
            "٣٩٨٫٢٥", "398.25", "تحليل وظائف الکلى"
        ):
            with self.subTest(raw=text):
                self.assertEqual(repair_service_spacing(text), text)

    def test_source_evidence_never_rewritten(self):
        d = {"invoice_items": [{"id": "it1", "service_name": {
            "raw": "تحليل دمشامل", "value": "تحليل دمشامل",
            "status": "extracted", "evidence_id": "source-1",
            "verification": "unverified",
        }, "quantity": {"value": 2}, "unit_price": {"value": 55}}],
        "evidence": [{"id": "source-1", "matched_text": "تحليل دمشامل"}],
        "requires_human_review": [{"field": "evidence", "reasons": ["paddle_line_geometry_only"]}],
        "warnings": [{"kind": "paddle_line_geometry_only"}]}
        before = copy.deepcopy(d)
        repair_document_service_names(d)
        row = d["invoice_items"][0]
        self.assertEqual(row["service_name"]["raw"], before["invoice_items"][0]["service_name"]["raw"])
        self.assertEqual(row["service_name"]["value"], "تحليل دم شامل")
        self.assertEqual(row["service_name"]["evidence_id"], "source-1")
        self.assertEqual(d["evidence"], before["evidence"])
        self.assertEqual(d["requires_human_review"], before["requires_human_review"])
        self.assertEqual(d["warnings"], before["warnings"])
        self.assertEqual(row["quantity"], before["invoice_items"][0]["quantity"])
        self.assertEqual(row["unit_price"], before["invoice_items"][0]["unit_price"])
        self.assertEqual(row["service_name"]["spacing_repair"]["original_value"], "تحليل دمشامل")

    def test_does_not_create_missing_medical_service_or_infer_its_name(self):
        d={"invoice_items": [
            {"service_name": {"status": "not_found", "value": None, "raw": None}},
            {"service_name": {"status": "extracted", "raw": "CreatinineTest",
                              "value": "CreatinineTest", "evidence_id": None}},
        ]}
        old=copy.deepcopy(d)
        repair_document_service_names(d)
        self.assertEqual(d,old)

    def test_provenance_and_other_clinical_names_not_touched(self):
        d={"invoice_items": [], "patient": {"name": {"raw": "ليلی حسن", "value": "ليلی حسن"}}}
        before=copy.deepcopy(d)
        repair_document_service_names(d)
        self.assertEqual(d,before)


if __name__ == "__main__":
    unittest.main()
