"""Independent, no-OCR invariants for the 300 NEW synthetic medical PDFs."""
import unittest
from decimal import Decimal
from collections import Counter
from scripts.benchmark_invoice300 import all_cases, LAYOUTS, SEED


class SyntheticHoldout300(unittest.TestCase):
    def test_exactly_300_distinct_new_invoices(self):
        cases = all_cases()
        self.assertEqual(len(cases), 300)
        self.assertEqual(len({c["id"] for c in cases}), 300)
        self.assertTrue(all(10 <= c["variant"] <= 59 for c in cases))
        self.assertEqual(Counter(c["layout"] for c in cases), Counter({x: 50 for x in LAYOUTS}))
        self.assertEqual(len({c["invoice_number"] for c in cases}), 300)
        self.assertEqual(SEED, 20261026)

    def test_ground_truth_arithmetic_not_guessed(self):
        for c in all_cases():
            line_sum = sum((Decimal(str(x["total"])) for x in c["rows"]), Decimal(0))
            total = line_sum - Decimal(str(c["discount"])) + Decimal(str(c["tax"]))
            discrepancy = Decimal("2") if c["printed_discrepancy"] else Decimal("0")
            self.assertEqual(total + discrepancy, Decimal(str(c["invoice_total"])))
            self.assertTrue(all(Decimal(str(row["qty"])) * Decimal(str(row["price"])) ==
                                Decimal(str(row["total"])) for row in c["rows"]))

    def test_six_image_modes_and_two_page_invoices(self):
        cases = all_cases()
        modes = {c["representation"] for c in cases}
        self.assertEqual(modes, {"text", "scan", "blur", "skew", "lowcontrast", "jpeg"})
        self.assertEqual(sum(c["pages"] == 2 for c in cases), 30)
        self.assertEqual(sum(bool(c["printed_discrepancy"]) for c in cases), 30)


if __name__ == "__main__":
    unittest.main()
