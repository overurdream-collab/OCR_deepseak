"""Test only observed printed totals; a prose number cannot replace one."""
import unittest
from types import SimpleNamespace

from mdia.total_candidates import is_isolated_total
from mdia.textutil import last_amount


def kv(*words):
    return SimpleNamespace(value_words=[SimpleNamespace(text=x) for x in words])


class GrandTotalCandidateTests(unittest.TestCase):
    def test_standalone_number(self):
        self.assertTrue(is_isolated_total(kv("2136.50")))
        self.assertTrue(is_isolated_total(kv("SAR","2136.50")))
        self.assertTrue(is_isolated_total(kv("٢١٣٦٫٥٠")))

    def test_explanatory_sentence_is_not_invoice_total(self):
        self.assertFalse(is_isolated_total(kv("deliberately","differs","by","2.00")))
        self.assertFalse(is_isolated_total(kv("synthetic","total","2.00")))
        self.assertFalse(is_isolated_total(kv("difference","2.00")))
        self.assertIsNotNone(last_amount("deliberately differs by 2.00")[1])

    def test_cannot_select_two_amounts(self):
        self.assertFalse(is_isolated_total(kv("200.00","2.00")))
        self.assertFalse(is_isolated_total(kv("Total","2.00")))

    def test_no_calculated_fallback(self):
        self.assertFalse(is_isolated_total(kv("word")))
        self.assertFalse(is_isolated_total(kv()))
        self.assertFalse(is_isolated_total(kv("2","%")))


if __name__ == "__main__":
    unittest.main()
