"""A completed OCR run must not be confused with perfect extraction."""
import copy
import unittest

from scripts.benchmark_invoice300 import VERSION, SEED, all_cases
from scripts.summarize_invoice300 import summarize


def complete_report():
    results = []
    for case in all_cases():
        fields = ["patient.name", "invoice.number", "invoice.total"]
        fields += [f"item.{i}.{key}" for i in range(1, len(case["rows"]) + 1)
                   for key in ("name", "qty", "price", "total")]
        results.append({"case": case["id"], "layout": case["layout"],
                        "model": "paddle_arabic", "real_paddle_detected": True,
                        "extra_item_rows": 0, "checks": [
                            {"field": field, "matched": True, "linked_evidence": True}
                            for field in fields]})
    return {"version": VERSION, "seed": SEED,
            "status": "completed_real_ocr", "results": results}


class SummaryTests(unittest.TestCase):
    def test_all_invoices_and_evidence_required(self):
        report = complete_report()
        result = summarize([report])
        self.assertEqual(result["expected"], 5776)
        self.assertTrue(result["accepted_100_percent"])
        report["results"][0]["checks"][0]["linked_evidence"] = False
        self.assertFalse(summarize([report])["accepted_100_percent"])

    def test_green_completion_with_errors_is_not_acceptance(self):
        report = complete_report()
        report["results"][0]["checks"][0]["matched"] = False
        report["results"][0]["extra_item_rows"] = 1
        result = summarize([report])
        self.assertFalse(result["accepted_100_percent"])
        self.assertEqual(result["correct"], 5775)
        self.assertEqual(result["errors_by_field"], {"patient.name": 1})

    def test_partial_duplicate_and_incompatible_reports_rejected(self):
        report = complete_report()
        with self.assertRaises(ValueError):
            summarize([report, report])
        for change in ("partial", "version", "fields"):
            broken = copy.deepcopy(report)
            if change == "partial":
                broken["results"].pop()
            elif change == "version":
                broken["version"] = "different"
            else:
                broken["results"][0]["checks"].pop()
            with self.assertRaises(ValueError):
                summarize([broken])

    def test_missing_real_engine_cannot_pass(self):
        report = complete_report()
        report["results"][0]["real_paddle_detected"] = False
        self.assertFalse(summarize([report])["accepted_100_percent"])
