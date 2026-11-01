"""Arabic/Persian OCR script variants: normalize *value*, retain raw evidence."""
import unittest

from mdia.extract import Ctx
from mdia.model import Page, Word
from mdia.textutil import (has_ambiguous_final_farsi_yeh,
                           normalize_arabic_ocr_script, uncertain_arabic_ocr_letters)
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

    def test_farsi_yeh_is_ambiguous_at_end_of_a_word(self):
        # Persian U+06CC has the same final glyph as Arabic alef maqsura
        # U+0649, but the same medial glyph as Arabic yeh U+064A.
        # Neither Arabic target can be inferred from a final/isolated glyph.
        self.assertEqual(normalize_arabic_ocr_script("کلی"), "كلی")
        self.assertEqual(normalize_arabic_ocr_script("علی، ی"), "علی، ی")
        self.assertEqual(normalize_arabic_ocr_script("کلی. علی"), "كلی. علی")
        self.assertTrue(has_ambiguous_final_farsi_yeh("کلی."))
        self.assertTrue(has_ambiguous_final_farsi_yeh("ی"))

    def test_farsi_yeh_in_joining_positions_remains_reviewable_arabic_yeh(self):
        self.assertEqual(normalize_arabic_ocr_script("یوم تحلیل"), "يوم تحليل")
        self.assertEqual(normalize_arabic_ocr_script("کلیِ ي"), "كلیِ ي")
        self.assertEqual(normalize_arabic_ocr_script("یَوم"), "يَوم")
        self.assertFalse(has_ambiguous_final_farsi_yeh("یَوم تحلیل"))
        self.assertTrue(has_ambiguous_final_farsi_yeh("یء"))

    def test_arabic_kaf_yeh_and_alef_maqsura_keep_distinct_codepoints(self):
        # Initial/medial/final shapes of kaf are font shaping, not character
        # substitutions.  The last two spellings are NOT interchangeable.
        for raw in ("كلى", "كلي", "كِلى", "الكلى", "كلوي"):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_arabic_ocr_script(raw), raw)
                f, _ = field(raw)
                self.assertEqual(f["raw"], raw)
                self.assertEqual(f["value"], raw)
                self.assertNotIn("ambiguous_final_farsi_yeh", f.get("review_reasons", []))

    def test_ambiguous_final_farsi_yeh_requires_review_even_without_rewrite(self):
        f, ev = field("علی")
        self.assertEqual(f["raw"], "علی")
        self.assertEqual(f["value"], "علی")
        self.assertEqual(f["verification"], "needs_review")
        self.assertIn("ambiguous_final_farsi_yeh", f["review_reasons"])
        self.assertNotIn("arabic_ocr_script_variant", f["review_reasons"])
        self.assertEqual(ev[0]["matched_text"], "علی")

    def test_mixed_kaf_and_ambiguous_yeh_preserves_raw_and_flags_both(self):
        f, ev = field("کلی")
        self.assertEqual(f["raw"], "کلی")
        self.assertEqual(f["value"], "كلی")
        self.assertEqual(f["verification"], "needs_review")
        self.assertIn("ambiguous_final_farsi_yeh", f["review_reasons"])
        self.assertIn("arabic_ocr_script_variant", f["review_reasons"])
        self.assertEqual(ev[0]["matched_text"], "کلی")

    def test_recognizes_other_urdu_persian_letters_without_equating_them(self):
        self.assertEqual(set(uncertain_arabic_ocr_letters("پ چ ژ گ ں ہ ھ ۃ ے")),
                         set("پچژگںہھۃے"))
        self.assertEqual(uncertain_arabic_ocr_letters("ك ي ک ی ء أ إ آ ة ى"), [])

    def test_urdu_character_is_reviewed_but_never_replaced(self):
        f, ev = field("گرفتن")
        self.assertEqual(f["value"], "گرفتن")
        self.assertEqual(f["raw"], "گرفتن")
        self.assertEqual(ev[0]["matched_text"], "گرفتن")
        self.assertEqual(f["verification"], "needs_review")
        self.assertIn("ocr_extended_arabic_letter", f["review_reasons"])

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
