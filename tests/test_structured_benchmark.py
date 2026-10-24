"""Deterministic evaluator regressions; no Paddle model download."""
import unittest
from scripts.compare_structured_arabic import evaluate, same, valid_evidence

def f(value, id="ev1"):
    return {"raw": str(value), "value": value, "evidence_id": id, "page": 1}

class StructuredBenchmarkTests(unittest.TestCase):
    def test_arabic_numbers_and_strict_names(self):
        self.assertTrue(same(500, "٥٠٠"))
        self.assertTrue(same("خالد يوسف", "خَالِد يُوسف"))
        self.assertFalse(same("خالد يوسف", "خالد"))
        self.assertFalse(same(1401, 1402))

    def test_reject_missing_or_invalid_evidence_boxes(self):
        doc = {"evidence": [{"id": "ev1", "page": 1,
                            "bbox": [.1, .2, .4, .3], "text": "خالد يوسف"}]}
        self.assertTrue(valid_evidence(f("خالد يوسف"), doc))
        self.assertFalse(valid_evidence(f("خالد يوسف", "missing"), doc))
        doc["evidence"][0]["bbox"] = [0, 0, 1.5, 1]
        self.assertFalse(valid_evidence(f("خالد يوسف"), doc))

    def test_wrong_row_amounts_never_count_as_correct(self):
        doc = {"document_type": "hospital_invoice", "patient": {"name": f("خالد يوسف")},
            "invoices": [{"invoice_number": f("INV-4004"), "invoice_total": f(1401)}],
            "invoice_items": [
                {"service_name": f("كشف استشاري"), "quantity": f(2),
                 "unit_price": f(75.5), "line_total": f(151)},
                {"service_name": f("تحليل دم شامل"), "quantity": f(1),
                 "unit_price": f(1250), "line_total": f(1250)}],
            "evidence": [{"id": "ev1", "page": 1, "bbox": [.1, .1, .4, .2], "text": "synthetic"}],
            "warnings": [], "requires_human_review": []}
        r = evaluate("invoice_shaped.pdf", {"documents": [doc], "processing_status": "completed"},
                     "tesseract", [{}])
        self.assertEqual((r["matched_fields"], r["total_fields"]), (6, 12))

    def test_paddle_estimated_positions_require_review(self):
        doc = {"document_type": "prescription", "patient": {"name": f("سارة عمر")},
            "medications": [], "evidence": [{"id": "ev1", "page": 1,
            "bbox": [.1, .2, .3, .4], "text": "سارة عمر"}],
            "warnings": [{"kind": "paddle_line_geometry_only"}],
            "requires_human_review": [{"reasons": ["paddle_line_geometry_only"]}]}
        r = evaluate("prescription_shaped.pdf",
                     {"documents": [doc], "processing_status": "completed_with_review"},
                     "paddle_arabic", [{"ocr_engine": "paddleocr-v5-arabic"}])
        self.assertTrue(r["paddle_model_used"] and r["paddle_human_review"])
        self.assertEqual(r["noninterpolated_word_boxes"], 0)

if __name__ == "__main__":
    unittest.main()
