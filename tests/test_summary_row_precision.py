"""Conservative summary-row exclusions; must not erase legitimate charges."""
import unittest
from mdia.model import Word, Line, Page
from mdia.tables import _is_summary_label, parse_table

def line(i, y, label, amount):
    words = [
        Word(label, .60, y, .83, y+.014),
        Word("1", .46, y, .49, y+.014),
        Word("50.00", .32, y, .39, y+.014),
        Word(amount, .10, y, .20, y+.014),
    ]
    return Line(1,i,sorted(words,key=lambda w:w.x0),rtl=True)

class SummaryRowTests(unittest.TestCase):
    # No amount may be inferred from a financial summary label.

    def test_only_exact_financial_summary_labels(self):
        for s in ("المجموع قبل الخصم", "الخصم", "الضريبة", "إجمالي الفاتورة", "Subtotal", "VAT", "Total"):
            self.assertTrue(_is_summary_label(s),s)
        for s in ("أجرة غرفة", "رسوم تمريض", "Room Charges", "Total Knee Replacement", "تحليل دم شامل"):
            self.assertFalse(_is_summary_label(s),s)

    def test_summary_excluded_but_real_service_preserved(self):
        page=Page(1,1,1,method="ocr")
        page.lines=[
            line(0,.20,"تحليل دم شامل","50.00"),
            line(1,.215,"الخصم","5.00"),
            line(2,.23,"أجرة غرفة","50.00"),
            line(3,.245,"إجمالي الفاتورة","95.00"),
        ]
        bounds=[("total",0,.25),("unit_price",.25,.43),("qty",.43,.55),("name",.55,1)]
        t=parse_table(page,None,kind="invoice",bounds=bounds,inherited=False,rtl=True)
        self.assertIsNotNone(t)
        self.assertEqual(len(t.rows),2)
        self.assertEqual([r.cells["name"][0].text for r in t.rows],["تحليل دم شامل","أجرة غرفة"])
        self.assertTrue({1,3}.issubset(t.line_idxs))

if __name__=="__main__":
    unittest.main()
