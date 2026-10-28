"""Arabic/Persian OCR script variants: normalize *value*, retain raw evidence."""
import unittest

from mdia.extract import Ctx
from mdia.model import Page, Word
from mdia.textutil import normalize_arabic_ocr_script
from scripts.compare_structured_arabic import row_by_name


def field(raw, method="ocr", kind="text"):
    word = Word(raw, .2, .3, .6, .33, .99, method,
                geometry_source="line_interpolated" if method == "ocr" else "native")
    page = Page(1, 1, 1, method=method, words=[word])
    page.flags["ocr_engine"] = "paddleocr-v5-arabic" if method == "ocr" else "pdf-text"
    context = Ctx("synthetic-job", "synthetic-doc", {1: page})
    return context.field(page, [word], kind=kind), context.evidence


class ArabicOCRScriptVariantTests(unittest.TestCase):
    def test_canonicalizes_only_visually_equivalent_arabic_letters(self):
        self.assertEqual(normalize_arabic_ocr_script("تحلیل سکر صائم"), "تحليل سكر صائم")
        self.assertEqual(normalize_arabic_ocr_script("کبسولات أموکسیسیلین"), "كبسولات أموكسيسيلين")

    def test_does_not_change_real_distinct_arabic_letters_or_digits(self):
        raw = "أجرة غرفة ١٢٥٫٥٠ غ پ گ ة ى"
        self.assertEqual(normalize_arabic_ocr_script(raw), raw)

    def test_ocr_value_is_normalized_but_raw_and_evidence_are_untouched(self):
        f, ev = field("تحلیل سکر صائم")
        self.assertEqual(f["raw"], "تحلیل سکر صائم")
        self.assertEqual(f["value"], "تحليل سكر صائم")
        self.assertEqual(f["verification"], "needs_review")
        self.assertIn("arabic_ocr_script_variant", f["review_reasons"])
        self.assertEqual(ev[0]["matched_text"], "تحلیل سکر صائم")
        self.assertEqual(ev[0]["id"], f["evidence_id"])
        self.assertEqual(ev[0]["geometry_source"], "line_interpolated")

    def test_pdf_text_layer_is_not_rewritten(self):
        f, ev = field("تحلیل سکر صائم", method="text-layer")
        self.assertEqual(f["raw"], f["value"])
        self.assertNotIn("arabic_ocr_script_variant", f.get("review_reasons", []))
        self.assertEqual(ev[0]["matched_text"], f["raw"])

    def test_canonical_value_recovers_same_row_without_copying_a_price(self):
        name, _ = field("تحلیل سکر صائم")
        rows = [{"service_name": name, "quantity": {"value": 1.0},
                 "unit_price": {"value": 160.5}, "line_total": {"value": 160.5}}]
        matched = row_by_name(rows, "service_name", "تحليل سكر صائم")
        self.assertIs(matched, rows[0])
        self.assertEqual(matched["unit_price"]["value"], 160.5)
        self.assertEqual(name["raw"], "تحلیل سکر صائم")

    def test_never_normalize_or_correct_financial_amounts(self):
        f, ev = field("۱۲۵٫۵۰", kind="money")
        self.assertEqual(f["raw"], "125٫50")  # existing numeric-digit parsing convention
        self.assertEqual(f["value"], 125.5)
        self.assertNotIn("arabic_ocr_script_variant", f.get("review_reasons", []))
        self.assertEqual(ev[0]["text"], "۱۲۵٫۵۰")  # source OCR text remains available


if __name__ == "__main__":
    unittest.main()
