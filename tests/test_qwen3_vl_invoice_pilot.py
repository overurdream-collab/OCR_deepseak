"""Model-free Qwen3-VL invoice test guards; no network downloads or patient data."""
import unittest

from scripts.qwen3_vl_invoice_pilot import (
    CASES, decimal_number, extract_json, norm_text, same_value, score_invoice,
)
from scripts.benchmark_invoice300 import new_case


class QwenPilotTests(unittest.TestCase):
    def test_synthetic_cases_have_unique_ids(self):
        ids = [f"{layout}_{index:02d}" for layout, index in CASES]
        self.assertEqual(len(ids), 8)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(10 <= index < 60 for _, index in CASES))

    def test_parse_generation_not_echoed_example(self):
        raw = ('user prompt {"patient_name":null,"invoice_number":null,'
               '"invoice_total":null,"items":[{"description":null}]}'
               '\nassistant {"patient_name":"خالد يوسف",'
               '"invoice_number":"INV-12345","invoice_total":49.75,'
               '"items":[{"description":"تحليل دم شامل",'
               '"quantity":"١","unit_price":"49.75","line_total":"49.75"}]}')
        got = extract_json(raw)
        self.assertEqual(got["invoice_number"], "INV-12345")

    def test_invalid_json_fails_visible(self):
        with self.assertRaisesRegex(ValueError, "no valid"):
            extract_json("the item is 150.00 but there is no JSON")
        with self.assertRaisesRegex(ValueError, "non-list"):
            extract_json('{"invoice_number":"INV-44","items":"unstructured"}')

    def test_arabic_and_western_amounts(self):
        self.assertEqual(decimal_number("١٬٢٣٤٫٥٠"), decimal_number("1,234.50"))
        self.assertTrue(same_value("550.25", "٥٥٠٫٢٥", numeric=True))
        self.assertFalse(same_value("160.25", None, numeric=True))
        self.assertIsNone(decimal_number("???"))
        self.assertEqual(norm_text("تَحْليل دم"), norm_text("تحليل دم"))

    def test_correct_exact_invoice_has_full_score(self):
        truth = new_case("ar_shaped", 14)
        pred = {
            "patient_name": truth["patient"],
            "invoice_number": truth["invoice_number"],
            "invoice_total": truth["invoice_total"],
            "items": [
                {"description": row["name"], "quantity": row["qty"],
                 "unit_price": row["price"], "line_total": row["total"]}
                for row in truth["rows"]
            ]
        }
        scored = score_invoice(truth, pred)
        self.assertEqual(scored["correct"], scored["expected"])
        self.assertEqual(scored["extra_rows"], 0)
        self.assertFalse(scored["inconsistent_predicted_rows"])
        self.assertTrue(scored["needs_human_review"])
        self.assertFalse(scored["source_word_boxes_verified"])

    def test_fabricated_amount_and_row_do_not_pass(self):
        truth = new_case("ar_visual", 17)
        pred = {
            "patient_name": truth["patient"],
            "invoice_number": truth["invoice_number"],
            "invoice_total": 11111111,
            "items": [
                {"description": r["name"], "quantity": r["qty"],
                 "unit_price": r["price"], "line_total": r["total"]}
                for r in truth["rows"]
            ] + [{"description": "Service not printed", "quantity": 1,
                  "unit_price": 99999, "line_total": 99999}]
        }
        scored = score_invoice(truth, pred)
        self.assertEqual(scored["extra_rows"], 1)
        self.assertFalse(next(x for x in scored["fields"]
                              if x["field"] == "invoice.total")["match"])
        self.assertEqual(scored["financial_values_auto_applied"], 0)

    def test_detect_internal_arithmetic_conflict_not_repair(self):
        truth = new_case("en_standard", 14)
        row = truth["rows"][0]
        pred = {"patient_name": truth["patient"],
                "invoice_number": truth["invoice_number"],
                "invoice_total": truth["invoice_total"],
                "items": [{"description": row["name"],
                           "quantity": 2, "unit_price": 10,
                           "line_total": 999}]}
        s = score_invoice(truth, pred)
        self.assertEqual(len(s["inconsistent_predicted_rows"]), 1)
        self.assertEqual(pred["items"][0]["line_total"], 999)

    def test_missing_fields_are_failures_not_predictions(self):
        truth = new_case("ar_mixed", 16)
        score = score_invoice(truth, {"items": [], "patient_name": None,
                                      "invoice_number": None, "invoice_total": None})
        self.assertEqual(score["correct"], 0)
        self.assertEqual(score["expected"], 3 + 4*len(truth["rows"]))
        self.assertEqual(len(score["unmatched_rows"]), len(truth["rows"]))


if __name__ == "__main__":
    unittest.main()
