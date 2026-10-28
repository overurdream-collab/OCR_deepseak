"""Reproduce verified OCR confusion U+060C versus decimal U+066B.

Never infer a separator when OCR output contains only bare digits.
Only OCR candidates with the observed Arabic comma may be numerically
interpreted, and they always require human review with raw evidence intact.
"""
import unittest

from mdia.extract import Ctx
from mdia.model import Page, Word
from mdia.textutil import (last_amount, ocr_arabic_comma_decimal,
                           is_numeric_token)


def field(text, *, method="ocr", kind="money"):
    p = Page(1, 600, 800, method=method,
             flags={"ocr_engine": "paddleocr-v5-arabic"} if method == "ocr" else {})
    w = Word(text, .20, .20, .33, .23, .92, method,
             geometry_source="line_interpolated" if method == "ocr" else "native")
    ctx = Ctx("syntheticjob", "syntheticdoc", {1: p})
    result = ctx.field(p, [w], kind=kind)
    return result, ctx.evidence


class ArabicCommaReviewTests(unittest.TestCase):
    def test_explicit_ocr_arabic_comma_is_candidate_not_approved(self):
        f, ev = field("٣٩٨،٢٥")
        self.assertEqual(f["value"], 398.25)
        self.assertEqual(f["raw"], "٣٩٨،٢٥")
        self.assertEqual(f["verification"], "needs_review")
        self.assertIn("ocr_arabic_comma_decimal_candidate", f["review_reasons"])
        self.assertEqual(ev[0]["matched_text"], "٣٩٨،٢٥")
        self.assertFalse(ev[0]["word_box_verified"])

    def test_ocr_number_has_same_review_requirement(self):
        f, _ = field("٣٩٨،٢٥", kind="number")
        self.assertEqual(f["value"], 398.25)
        self.assertEqual(f["verification"], "needs_review")

    def test_text_layer_arabic_comma_is_not_reinterpreted_as_ocr(self):
        f, _ = field("٣٩٨،٢٥", method="text-layer")
        self.assertIsNone(f["value"])
        self.assertEqual(f["status"], "unreadable")

    def test_bare_digits_must_not_be_repaired_by_guessing(self):
        f, _ = field("٢٥٦٢٥")
        self.assertEqual(f["value"], 25625.0)
        self.assertEqual(f["raw"], "٢٥٦٢٥")
        self.assertNotIn("ocr_arabic_comma_decimal_candidate", f.get("review_reasons", []))
        self.assertIsNone(ocr_arabic_comma_decimal("٢٥٦٢٥"))

    def test_prose_and_ambiguous_punctuation_rejected(self):
        for s in ("١٠، ٢٠", "٣٩٨،٢", "٣،١٢،٣٤", "SAR ٣٩٨،٢٥",
                  "٣٩٨،٢٥٠", "١٬٠٠٠،٢٥"):
            with self.subTest(source=s):
                self.assertIsNone(ocr_arabic_comma_decimal(s))
                if s != "١٠، ٢٠":
                    self.assertIsNone(last_amount(s)[1])

    def test_only_explicit_two_decimal_digit_token(self):
        self.assertEqual(ocr_arabic_comma_decimal("٣٩٨،٢٥"), 398.25)
        self.assertEqual(last_amount("٣٩٨،٢٥", allow_ocr_arabic_comma=True)[1], 398.25)
        self.assertTrue(is_numeric_token("٣٩٨،٢٥"))
        self.assertFalse(is_numeric_token("٣٩٨،٢"))

    def test_original_latin_and_arabic_decimal_separators_unchanged(self):
        for source in ("398.25", "٣٩٨٫٢٥"):
            with self.subTest(source=source):
                f, _ = field(source)
                self.assertEqual(f["value"], 398.25)
                self.assertNotIn("ocr_arabic_comma_decimal_candidate", f.get("review_reasons", []))


if __name__ == "__main__":
    unittest.main()
