"""Negative controls for receipt TOTAL selection (not financial approval)."""
import unittest

from benchmarks.public_documents.field_selector import (
    select_total, tess_lines, evaluate_selected,
)


def line(text, row=1):
    return {"text": text, "line_id": str(row), "bbox": [0, row, 100, row + 10],
            "confidence": 0.95}


class FieldSelectionTests(unittest.TestCase):
    def test_exact_unique_total_label(self):
        answer = select_total([line("SUBTOTAL 25.00"), line("TOTAL 31.00", 2)])
        self.assertEqual(answer["status"], "candidate")
        self.assertEqual(answer["value"], "31.00")
        self.assertEqual(answer["verification"], "provisional")
        self.assertEqual(evaluate_selected(answer, "31.00"), "correct")

    def test_occurrence_on_wrong_line_not_accepted(self):
        answer = select_total([line("SUBTOTAL 31.00"), line("TOTAL 13.00", 2)])
        self.assertEqual(evaluate_selected(answer, "31.00"), "wrong")

    def test_total_without_label_abstains(self):
        answer = select_total([line("Cash 31.00"), line("Card 10.00", 2)])
        self.assertEqual(evaluate_selected(answer, "31.00"), "abstained")

    def test_multiple_total_labels_abstain(self):
        answer = select_total([line("TOTAL 31.00"), line("TOTAL 31.00", 2)])
        self.assertEqual(answer["status"], "abstain")

    def test_multiple_values_on_total_line_abstain(self):
        self.assertEqual(select_total([line("TOTAL 31.00 32.00")])["status"], "abstain")

    def test_subtotal_excluded(self):
        self.assertEqual(select_total([line("SUB TOTAL 31.00")])["status"], "abstain")

    def test_balance_excluded(self):
        self.assertEqual(select_total([line("BALANCE TOTAL 31.00")])["status"], "abstain")

    def test_total_with_currency_token(self):
        answer = select_total([line("GRAND TOTAL RM 1,250.00")])
        self.assertEqual(evaluate_selected(answer, "1250.00"), "correct")

    def test_ambiguous_integer_total_abstains(self):
        self.assertEqual(select_total([line("TOTAL 2")])["status"], "abstain")

    def test_dollar_ground_truth_supported(self):
        choice = select_total([line("TOTAL $8.20")])
        self.assertEqual(evaluate_selected(choice, "$8.20"), "correct")

    def test_tesseract_line_location(self):
        data = {"text": ["TOTAL", "31.00", "OTHER"],
                "block_num": [1, 1, 2], "par_num": [1, 1, 1],
                "line_num": [1, 1, 1], "left": [10, 60, 10],
                "top": [20, 20, 50], "width": [45, 40, 60],
                "height": [15, 15, 15], "conf": ["99", "96", "10"]}
        lines = tess_lines(data)
        self.assertEqual(len(lines), 2)
        self.assertEqual(select_total(lines)["bbox"], [10, 20, 100, 35])


if __name__ == "__main__":
    unittest.main()
