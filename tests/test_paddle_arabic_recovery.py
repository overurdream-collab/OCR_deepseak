"""Regression tests for exact Arabic PaddleOCR strings. No model download and no patient data."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mdia.kv import line_pairs
from mdia.model import build_lines
from mdia.paddle_arabic import result_to_words
from mdia.pipeline import process_job
from mdia.store import Store
from scripts.compare_arabic_ocr import prepare


def simulated_ocr(lines, image_size):
    return result_to_words([{"res": {
        "rec_texts": lines,
        "rec_scores": [0.98] * len(lines),
        "rec_boxes": [[20, 45 + 32 * i, 700, 69 + 32 * i] for i in range(len(lines))],
    }}], image_size)


class ArabicRecovery(unittest.TestCase):
    def pairs(self, text):
        words = simulated_ocr([text], (800, 200))
        return [(p.id, p.value_text) for p in line_pairs(build_lines(words, 1)[0])]

    def test_reversed_complete_invoice_id(self):
        self.assertEqual(self.pairs("INV-4004:رقم الفاتورة"), [("invoice.number", "INV-4004")])

    def test_joined_patient_name(self):
        self.assertEqual(self.pairs("اسم المريضخالد يوسف"), [("patient.name", "خالد يوسف")])

    def test_corrupt_number_is_not_guessed(self):
        self.assertNotIn(("invoice.number", "INV-4004"), self.pairs("V-44رقمالفاتورة"))

    def test_medication_names_exclude_uncertain_list_markers_with_review(self):
        lines = ["عيادة النور", "وصفة ةطبية", "اسم المريض: سارة عمر",
                 "الطبيب :لیلی ناصر",
                 "١٠ أموكسيسيلين ٥٠٠ ملغ كبسولة مرتين يوميا لمدة ٧ أيام",
                 "٢٠ باراسيتامول ٥٠٠ ملغ قرص ثلاث مرات يوميا لمدة ٣ أيام"]
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            prepare(root / "pdf")
            name = "prescription_shaped.pdf"
            store = Store(root / "jobs")
            job_id = store.create(name, (root / "pdf" / name).read_bytes())
            with patch.dict("os.environ", {"MDIA_OCR_ENGINE": "paddle_arabic"}), \
                    patch("mdia.paddle_arabic.ocr_image",
                          side_effect=lambda img: simulated_ocr(lines, img.size)):
                result = process_job(store, job_id, ocr_mode="force")
            doc = result["documents"][0]
            self.assertEqual(doc["document_type"], "prescription")
            self.assertEqual([m["brand_name"]["value"] for m in doc["medications"]],
                             ["أموكسيسيلين", "باراسيتامول"])
            for medicine in doc["medications"]:
                field = medicine["brand_name"]
                self.assertEqual(field["verification"], "needs_review")
                self.assertIn("ocr_list_prefix_removed_needs_review", field.get("review_reasons", []))
                self.assertIsNotNone(field["evidence_id"])
            self.assertTrue(doc["requires_human_review"])
