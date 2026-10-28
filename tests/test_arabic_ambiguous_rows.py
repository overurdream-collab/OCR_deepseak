"""Conservative recovery of rows where OCR reads quantities as letters.

The entire printed service name, price, and line amount must have independent
source words in the SAME line. A source-letter quantity remains unreadable
unless original-image secondary OCR independently confirms the printed digit.
"""
import unittest

from mdia.extract import Ctx
from mdia.quantity_reocr import choose_digit
from mdia.tables import unheaded_arabic_invoice_rows
from tests.test_arabic_missing_rows import line, page


class ArabicAmbiguousRowTests(unittest.TestCase):
    def fixture(self, glyph):
        return [
            line(0, .176, "تخطيط قلب", glyph, "59.25", "177.75"),
            line(1, .198, "كشف استشاري", "2", "216.25", "432.50"),
            line(2, .219, "تحليل دم شامل", "4", "97.00", "388.00"),
            line(3, .241, "أقراص باراسيتامول", "1", "240.75", "240.75"),
        ]

    def test_observed_nonnumeric_glyphs_preserve_source_and_row(self):
        for glyph in ("M", "H", "w", "R", "I"):
            with self.subTest(glyph=glyph):
                p = page(self.fixture(glyph))
                t = unheaded_arabic_invoice_rows(p)
                self.assertEqual(len(t.rows), 4)
                first = t.rows[0]
                self.assertEqual(first.line_idxs, [0])
                self.assertEqual(first.cells["qty"][0].text, glyph)
                self.assertEqual(first.cells["unit_price"][0].text, "59.25")
                self.assertEqual(first.cells["total"][0].text, "177.75")
                ctx = Ctx("synthetic", "case1", {1:p})
                q = ctx.field(p, first.cells["qty"], kind="number")
                self.assertEqual(q["raw"], glyph)
                self.assertIsNone(q["value"])
                self.assertEqual(q["verification"], "needs_review")

    def test_second_engine_is_not_replaced_by_arithmetic_guess(self):
        self.assertIsNone(choose_digit([], 59.25, 177.75, orig_token="w"))
        self.assertIsNone(choose_digit([], 59.25, 177.75, orig_token="H"))

    def test_exclude_unproven_glyphs_and_missing_price(self):
        for glyph in ("-", "–", "/", "N", "°"):
            with self.subTest(glyph=glyph):
                t = unheaded_arabic_invoice_rows(page(self.fixture(glyph)))
                self.assertEqual(len(t.rows), 3)

        lines = self.fixture("w")
        lines[0].words = [word for word in lines[0].words if word.text != "59.25"]
        t = unheaded_arabic_invoice_rows(page(lines))
        self.assertEqual(len(t.rows), 3)

    def test_low_confidence_wrong_column_and_no_anchor_fail_closed(self):
        for glyph in ("H", "w", "R", "I"):
            with self.subTest(glyph=glyph):
                lines = self.fixture(glyph)
                lines[0] = line(0,.176,"تخطيط قلب",glyph,"59.25","177.75",
                                qty_conf=.29)
                self.assertEqual(len(unheaded_arabic_invoice_rows(page(lines)).rows),3)
                lines = self.fixture(glyph)
                lines[0] = line(0,.176,"تخطيط قلب",glyph,"59.25","177.75",
                                qty_x=.60)
                self.assertEqual(len(unheaded_arabic_invoice_rows(page(lines)).rows),3)
                lines = self.fixture(glyph)[:3]  # Only two confirmed rows exist
                self.assertEqual(len(unheaded_arabic_invoice_rows(page(lines)).rows),3)
                lines = self.fixture(glyph)[:2]  # Only one confirmed row exists
                self.assertEqual(len(unheaded_arabic_invoice_rows(page(lines)).rows),1)

    def test_summary_caption_with_ambiguous_glyph_not_billed(self):
        lines = self.fixture("w")
        lines.insert(0, line(9, .157, "إجمالي الفاتورة", "H", "59.25", "177.75"))
        t = unheaded_arabic_invoice_rows(page(lines))
        self.assertEqual(len(t.rows),4)


if __name__ == "__main__":
    unittest.main()
