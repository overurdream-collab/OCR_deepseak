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

if __name__=="__main__":
    unittest.main()
