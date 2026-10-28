"""Source-grounded Arabic unheaded table recovery when OCR reads qty as M.

Synthetic geometry only; human review mandatory. Never derive a quantity from
prices, totals, service names, arithmetic or invoice-level ground truth.
"""
import unittest

from mdia.extract import Ctx
from mdia.model import Line, Page, Word
from mdia.tables import unheaded_arabic_invoice_rows
from mdia.textutil import parse_number


def w(text, x0, x1, y, conf=.92):
    return Word(text, x0, y-.007, x1, y+.007, conf, "ocr",
                geometry_source="line_interpolated")


def line(idx, y, name, qty, price, total,
         *, qty_x=.475, qty_conf=.95, price_x=.335, total_x=.165):
    words = [
        w(name, .82, .95, y),
        w(qty, qty_x-.008, qty_x+.008, y, qty_conf),
        w(price, price_x-.031, price_x+.031, y),
        w(total, total_x-.035, total_x+.035, y),
    ]
    return Line(1, idx, sorted(words, key=lambda v: v.x0), rtl=True)


def page(lines):
    p = Page(1, 600, 800, method="ocr",
             flags={"ocr_engine":"paddleocr-v5-arabic"})
    p.lines = list(lines)
    p.words = [v for ln in lines for v in ln.words]
    return p


class MissingQuantityTests(unittest.TestCase):
    def full_rows(self):
        return [
            line(0,.176,"تخطيط قلب","M","59.25","177.75"),
            line(1,.198,"كشف استشاري","M","216.25","648.75"),
            line(2,.219,"تحليل دم شامل","4","97.00","388.00"),
            line(3,.241,"أقراص باراسيتامول","1","240.75","240.75"),
            line(4,.262,"أجرة غرفة","1","182.50","182.50"),
        ]

    def test_recovers_only_observed_service_and_amounts(self):
        p = page(self.full_rows())
        table = unheaded_arabic_invoice_rows(p)
        self.assertEqual(len(table.rows), 5)
        self.assertEqual([row.line_idxs for row in table.rows], [[0],[1],[2],[3],[4]])
        for i in (0, 1):
            cells = table.rows[i].cells
            self.assertEqual(cells["qty"][0].text, "M")
            self.assertIsNone(parse_number(cells["qty"][0].text))
            self.assertEqual(cells["name"][0].text, self.full_rows()[i].words[-1].text)
            self.assertTrue(table.rows[i].inherited)
        self.assertEqual(table.rows[0].cells["unit_price"][0].text, "59.25")
        self.assertEqual(table.rows[1].cells["total"][0].text, "648.75")

    def test_unreadable_quantity_keeps_original_evidence_and_review(self):
        p = page(self.full_rows())
        t = unheaded_arabic_invoice_rows(p)
        ctx = Ctx("testjob", "testdoc", {1: p})
        qty = ctx.field(p, t.rows[0].cells["qty"], kind="number")
        self.assertEqual(qty["raw"], "M")
        self.assertIsNone(qty["value"])
        self.assertEqual(qty["status"], "unreadable")
        self.assertEqual(qty["verification"], "needs_review")
        price = ctx.field(p, t.rows[0].cells["unit_price"], kind="money")
        self.assertEqual(price["value"], 59.25)
        self.assertEqual(ctx.evidence[-1]["text"], "59.25")

    def test_no_two_independent_anchor_rows_fails_closed(self):
        p = page(self.full_rows()[:3])  # only the third row has a real quantity
        t = unheaded_arabic_invoice_rows(p)
        self.assertEqual(len(t.rows), 1)

    def test_stray_letter_outside_quantity_column_rejected(self):
        lines = self.full_rows()
        lines[0] = line(0,.176,"تخطيط قلب","M","59.25","177.75",qty_x=.60)
        t = unheaded_arabic_invoice_rows(page(lines))
        self.assertEqual(len(t.rows), 4)

    def test_unproven_letter_or_low_confidence_never_repaired(self):
        for quantity,confidence in [("N",.96),("M",.30)]:
            with self.subTest(quantity=quantity, confidence=confidence):
                lines = self.full_rows()
                lines[0] = line(0,.176,"تخطيط قلب",quantity,"59.25","177.75",
                                qty_conf=confidence)
                t = unheaded_arabic_invoice_rows(page(lines))
                self.assertEqual(len(t.rows), 4)

    def test_missing_price_cannot_borrow_from_nearby_row(self):
        lines = self.full_rows()
        ln = lines[0]
        ln.words = [ww for ww in ln.words if ww.text != "59.25"]
        t = unheaded_arabic_invoice_rows(page(lines))
        self.assertEqual(len(t.rows), 4)
        self.assertFalse(any(0 in row.line_idxs for row in t.rows))

    def test_summary_with_marker_not_billed(self):
        lines = self.full_rows()
        lines.insert(0, line(5,.155,"إجمالي الفاتورة","M","30.00","50.00"))
        t = unheaded_arabic_invoice_rows(page(lines))
        self.assertEqual(len(t.rows), 5)

    def test_does_not_operate_on_native_pdf_text(self):
        p = page(self.full_rows())
        p.method = "text-layer"
        self.assertIsNone(unheaded_arabic_invoice_rows(p))


if __name__ == "__main__":
    unittest.main()
