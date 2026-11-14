"""Simple synthetic tests for the diagnostic classification (no inference)."""
import unittest

from scripts.diagnose_arabic_decimal_ocr import classify_field


class NumericDiagnosticTests(unittest.TestCase):
    def test_true_decimal_loss_is_flagged(self):
        self.assertEqual(classify_field({"matched": False, "field": "item.3.price",
                                         "expected": 83.25, "actual": 8325.0}),
                         "suspected_decimal_separator_loss_100x")

    def test_invoice_total_not_corrected(self):
        f = {"matched": False, "field": "invoice.total",
             "expected": 1286.0, "actual": 128600.0}
        self.assertEqual(classify_field(f), "suspected_decimal_separator_loss_100x")
        self.assertEqual(f["actual"], 128600.0)

    def test_missing_vs_wrong(self):
        self.assertEqual(classify_field({"matched": False, "field": "item.1.qty",
                                         "expected": 2, "actual": None}), "missing")
        self.assertEqual(classify_field({"matched": False, "field": "item.1.qty",
                                         "expected": 2, "actual": 3}), "incorrect")

    def test_never_assume_numeric_ratio_for_text_names(self):
        self.assertEqual(classify_field({"matched": False, "field": "patient.name",
                                         "expected": "ليلى", "actual": "ليلي"}), "incorrect")

    def test_correct_unchanged(self):
        self.assertEqual(classify_field({"matched": True, "field": "item.1.total",
                                         "expected": 12.50, "actual": 12.50}), "correct")


if __name__ == "__main__":
    unittest.main()
