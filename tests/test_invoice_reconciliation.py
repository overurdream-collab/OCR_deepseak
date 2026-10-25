import unittest
from mdia.invoice_reconciliation import reconcile

class ReconciliationTests(unittest.TestCase):
    def test_valid_evidence(self):
        row={"description":"تحليل دم", "quantity":"٢", "unit_price":"١٠٫٥٠", "line_total":"٢١"}
        result=reconcile([row], ["تحليل دم","2","10.50","21.00"])
        self.assertEqual(result[0]["reasons"], [])
        self.assertEqual(result[0]["original_row"], row)
    def test_fabricated_price_is_not_accepted(self):
        row={"description":"كشف", "quantity":1,"unit_price":"999","line_total":"999"}
        result=reconcile([row], ["كشف","1","50","50"])
        self.assertIn("no_source_evidence_unit_price",result[0]["reasons"])
        self.assertTrue(result[0]["review_required"])
    def test_math_mismatch_only_flags(self):
        row={"description":"كشف","quantity":2,"unit_price":10,"line_total":19}
        r=reconcile([row], ["كشف","2","10","19"])
        self.assertIn("arithmetic_mismatch",r[0]["reasons"])
        self.assertEqual(r[0]["original_row"]["line_total"],19)
    def test_missing_never_filled(self):
        r=reconcile([{"description":"تحليل","quantity":None,"unit_price":12,"line_total":12}],["تحليل","12"])
        self.assertIn("missing_quantity",r[0]["reasons"])
