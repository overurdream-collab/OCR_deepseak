"""A second OCR engine is never promoted just because its average score rises."""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_invoice300_acceptance import EXPECTED_CASES, SEED, VERSION, InvalidReport
from scripts.compare_invoice300_engines import compare_runs, load_run


FIELDS = ("patient.name", "invoice.number", "invoice.total", "item.1.name",
          "item.1.qty", "item.1.price", "item.1.total")


def record(case_id, engine):
    layout, _ = EXPECTED_CASES[case_id]
    return {"case": case_id, "layout": layout, "model": engine,
            "real_paddle_detected": engine == "paddle_arabic", "page_failures": [],
            "review_required": True, "expected_item_rows": 1,
            "extracted_item_rows": 1, "extra_item_rows": 0,
            "matched_item_names": 1, "total": 7, "matched": 7,
            "with_evidence": 7,
            "checks": [{"field": field, "expected": "synthetic", "actual": "synthetic",
                        "matched": True, "linked_evidence": True} for field in FIELDS]}


def update_checks(row):
    row["matched"] = sum(c["matched"] for c in row["checks"])
    row["with_evidence"] = sum(c["linked_evidence"] for c in row["checks"])
    row["matched_item_names"] = int(row["checks"][3]["matched"])
    row["extra_item_rows"] = max(0, row["extracted_item_rows"] - row["matched_item_names"])


class EngineComparisonTests(unittest.TestCase):
    def setUp(self):
        self.primary = {case: record(case, "paddle_arabic") for case in EXPECTED_CASES}
        self.candidate = {case: record(case, "tesseract") for case in EXPECTED_CASES}

    def test_exact_match_only_allows_nonregression_without_losses(self):
        result = compare_runs(self.primary, self.candidate)
        self.assertEqual(result["status"], "NONREGRESSION_PASS")
        self.assertEqual(result["totals"]["fields"], 2100)
        self.assertEqual(result["totals"]["both_wrong"], 0)
        self.assertTrue(result["oracle_is_not_deployable"])

    def test_candidate_financial_regression_blocks_promotion_even_with_gain(self):
        case = "en_standard_10"
        self.primary[case]["checks"][4].update(matched=False, linked_evidence=False)
        self.candidate[case]["checks"][5].update(matched=False, linked_evidence=False)
        update_checks(self.primary[case]); update_checks(self.candidate[case])
        result = compare_runs(self.primary, self.candidate)
        self.assertEqual(result["status"], "BLOCKED_FOR_AUTOMATIC_REPLACEMENT")
        self.assertEqual(result["totals"]["candidate_only_correct"], 1)
        self.assertEqual(result["totals"]["primary_only_correct"], 1)
        self.assertEqual(result["financial_fields_lost_by_candidate"], 1)
        self.assertEqual(result["recommendation"], "review_only_second_opinion")

    def test_expected_truth_cannot_differ_between_models(self):
        self.candidate["ar_mixed_49"]["checks"][0]["expected"] = "different ground truth"
        with self.assertRaisesRegex(InvalidReport, "unaligned ground truth"):
            compare_runs(self.primary, self.candidate)

    def test_missing_review_guard_blocks_even_with_no_accuracy_loss(self):
        self.candidate["en_standard_10"]["review_required"] = False
        result = compare_runs(self.primary, self.candidate)
        self.assertEqual(result["status"], "BLOCKED_FOR_AUTOMATIC_REPLACEMENT")
        self.assertEqual(result["review_regression_case_count"], 1)
        self.assertEqual(result["regressed_case_count"], 0)

    def test_requires_complete_300_case_identity_map(self):
        del self.candidate["ar_shaped_10"]
        with self.assertRaisesRegex(InvalidReport, "incomplete"):
            compare_runs(self.primary, self.candidate)

    def test_load_run_rejects_incomplete_or_tampered_shard(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for shard in range(6):
                rows = [r for case, r in self.primary.items()
                        if EXPECTED_CASES[case][1] == shard]
                path = Path(tmp) / f"shard{shard}.json"
                obj = {"seed": SEED, "version": VERSION, "status": "completed_real_ocr",
                       "cases": 50, "shard": shard, "shards": 6,
                       "engines": ["paddle_arabic"], "failure_records": [],
                       "summary": {"paddle_arabic": {"documents": 50, "matched": 350,
                                                    "expected": 350,
                                                    "extra_item_rows": 0, "failures": 0}},
                       "results": rows}
                path.write_text(json.dumps(obj), encoding="utf-8")
                paths.append(path)
            self.assertEqual(len(load_run(paths, "paddle_arabic")), 300)
            with self.assertRaisesRegex(InvalidReport, "six shard files"):
                load_run(paths[:5], "paddle_arabic")
            tampered = json.loads(paths[2].read_text(encoding="utf-8"))
            tampered["seed"] = -1
            paths[2].write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(InvalidReport, "wrong seed"):
                load_run(paths, "paddle_arabic")


if __name__ == "__main__":
    unittest.main()
