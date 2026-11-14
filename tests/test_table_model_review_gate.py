"""Safety tests for a review-only PP-StructureV3 table candidate."""
import unittest

from scripts.table_model_review_gate import InvalidTable, exact_decimal, parse_html, review_table

COLS = {"name": 3, "qty": 2, "unit_price": 1, "total": 0}


def doc(html):
    return {"res": {"table_res_list": [{"pred_html": html, "cell_box_list": []}]}}


def row(name="تحليل كلى", qty="٢", price="١٠٫٥٠", total="٢١٫٠٠"):
    return ("<tr><td>" + total + "</td><td>" + price + "</td><td>" + qty + "</td><td>" + name + "</td></tr>")


class GateTests(unittest.TestCase):
    def test_full_arabic_eastern_digits_and_original_values_preserved(self):
        result = review_table(doc("<table>" + row() + "</table>"), COLS)
        self.assertEqual(result["status"], "BLOCKED_FOR_AUTOMATIC_PROMOTION")
        self.assertEqual(result["suggestions"][0]["raw_cells"],
                         {"name": "تحليل كلى", "qty": "٢", "unit_price": "١٠٫٥٠", "total": "٢١٫٠٠"})
        self.assertFalse(result["suggestions"][0]["matched_original_word_boxes"])
        self.assertIs(result["financial_values_modified"], False)

    def test_arithmetic_is_warning_only(self):
        candidate = review_table(doc("<table>" + row(total="٢٠٫٠٠") + "</table>"), COLS)
        self.assertIn("printed_arithmetic_mismatch", candidate["suggestions"][0]["review_reasons"])
        self.assertEqual(candidate["suggestions"][0]["raw_cells"]["total"], "٢٠٫٠٠")

    def test_rejects_cross_row_borrowing(self):
        html = "<table>" + row(name="كشف", qty="١", price="١٠", total="١٠") + row(name="دواء", qty="٢", price="", total="٢٠") + "</table>"
        result = review_table(doc(html), COLS)
        self.assertEqual(len(result["suggestions"]), 2)
        self.assertIn("missing_cell", result["suggestions"][1]["review_reasons"])
        self.assertEqual(result["suggestions"][1]["raw_cells"]["unit_price"], "")

    def test_ambiguous_separator_does_not_guess_amount(self):
        for s in ("١٬٠٠٠", "1,000", "١٫٢.٣", "SAR 5", "1.2.3"):
            with self.subTest(value=s):
                self.assertIsNone(exact_decimal(s))
        result = review_table(doc("<table>" + row(price="1,000") + "</table>"), COLS)
        self.assertIn("ambiguous_or_unreadable_number", result["suggestions"][0]["review_reasons"])

    def test_refuses_missing_table_region(self):
        with self.assertRaisesRegex(InvalidTable, "no table_res_list"):
            review_table({"table_res_list": []}, COLS)

    def test_refuses_implicit_or_overlapping_column_maps(self):
        html = doc("<table>" + row() + "</table>")
        with self.assertRaises(InvalidTable):
            review_table(html, {"name": 0})
        with self.assertRaises(InvalidTable):
            review_table(html, {"name": 0, "qty": 0, "unit_price": 2, "total": 3})

    def test_refuses_html_spans_and_nesting(self):
        for html in ('<table><tr><td colspan="2">خدمة</td></tr></table>',
                     '<table><tr><td><table><tr><td>x</td></tr></table></td></tr></table>'):
            with self.subTest(html=html):
                with self.assertRaises(InvalidTable):
                    parse_html(html)

    def test_invalid_one_table_is_reported_without_affecting_other(self):
        source = {"table_res_list": [
            {"pred_html": '<table><tr><td rowspan="2">x</td></tr></table>'},
            {"pred_html": '<table>' + row() + '</table>'},
        ]}
        result = review_table(source, COLS)
        self.assertEqual(len(result["problems"]), 1)
        self.assertEqual(len(result["suggestions"]), 1)
        self.assertEqual(result["suggestions"][0]["table_index"], 1)

    def test_can_explicitly_skip_header_row(self):
        html = "<table><tr><th>الإجمالي</th><th>السعر</th><th>الكمية</th><th>الوصف</th></tr>" + row() + "</table>"
        result = review_table(doc(html), COLS, first_data_row=1)
        self.assertEqual(len(result["suggestions"]), 1)
        self.assertEqual(result["suggestions"][0]["row_index"], 1)

    def test_never_asserts_original_word_boxes_even_if_cell_boxes_present(self):
        src = doc('<table>' + row() + '</table>')
        src["res"]["table_res_list"][0]["cell_box_list"] = [[0, 0, 20, 20]] * 4
        result = review_table(src, COLS)
        self.assertEqual(result["verified_source_boxes"], 0)
        self.assertFalse(result["suggestions"][0]["matched_original_word_boxes"])

    def test_zero_negative_or_non_numeric_values_warn(self):
        for qty in ("0", "-2", "غير واضح"):
            with self.subTest(qty=qty):
                result = review_table(doc("<table>" + row(qty=qty) + "</table>"), COLS)
                self.assertTrue(any(x in result["suggestions"][0]["review_reasons"]
                                    for x in ("unexpected_negative_or_zero", "ambiguous_or_unreadable_number")))


if __name__ == "__main__":
    unittest.main()
