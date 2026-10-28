"""Geometry checks must not manufacture invoice amounts."""
import unittest
from mdia.model import Word
from mdia.tables import _invoice_cell_geometry_safe

def w(t,x):
    return Word(t,x,.1,x+.04,.12)

class CellGuardTests(unittest.TestCase):
    def test_normal_numeric_cells(self):
        self.assertTrue(_invoice_cell_geometry_safe({
            "name":[w("تحليل",.7)],"qty":[w("2",.4)],
            "unit_price":[w("10.50",.25)],"total":[w("21.00",.1)]},[]))
    def test_split_number_is_ambiguous(self):
        self.assertFalse(_invoice_cell_geometry_safe({
            "qty":[w("2",.4)],"total":[w("1",.1),w("00",.15)]},[]))
    def test_unparseable_amount_is_ambiguous(self):
        self.assertFalse(_invoice_cell_geometry_safe({
            "qty":[w("2",.4)],"total":[w("??",.1)]},[]))
    def test_missing_amount_not_fabricated(self):
        self.assertTrue(_invoice_cell_geometry_safe({"qty":[w("2",.4)]},[]))

    def test_printed_currency_is_not_a_second_amount(self):
        self.assertTrue(_invoice_cell_geometry_safe({
            "unit_price": [w("SAR", .2), w("300.00", .25)],
            "total": [w("300.00", .1), w("ريال", .15)]}, []))

    def test_currency_does_not_hide_two_amounts(self):
        self.assertFalse(_invoice_cell_geometry_safe({
            "total": [w("SAR", .1), w("1", .15), w("00", .2)]}, []))

    def test_unknown_text_is_not_a_currency_label(self):
        self.assertFalse(_invoice_cell_geometry_safe({
            "total": [w("unknown", .1), w("300.00", .15)]}, []))

if __name__=="__main__":
    unittest.main()
