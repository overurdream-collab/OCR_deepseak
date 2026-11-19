"""Coverage metric should not treat joined page digits as a matching amount."""
import unittest

from benchmarks.public_documents.sroie_benchmark import (
    norm_amount, total_token_present,
)


class PublicBenchmarkMetricTests(unittest.TestCase):
    def test_exact_total_token(self):
        self.assertTrue(total_token_present("SUB TOTAL 20.00\nTOTAL 31.00\n", "31.00"))

    def test_page_concat_false_positive_rejected(self):
        self.assertFalse(total_token_present("12\n34\n56", "23.45"))

    def test_embedded_digits_not_matching_total(self):
        self.assertFalse(total_token_present("number 1031.00", "31.00"))

    def test_thousands_separator(self):
        self.assertTrue(total_token_present("TOTAL $ 1,250.00", "1250.00"))

    def test_invalid_total_not_accepted(self):
        self.assertFalse(total_token_present("total 1.2.3", "1.2.3"))

    def test_decimal_value(self):
        self.assertEqual(str(norm_amount("31.00")), "31.00")


if __name__ == "__main__":
    unittest.main()
