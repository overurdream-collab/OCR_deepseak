"""Fast contract tests. Synthetic score fixtures only; no OCR or patient data."""
import copy
import io
import json
import re
import tempfile
import unittest
from collections import defaultdict
from contextlib import redirect_stdout
from pathlib import Path

from scripts.benchmark_invoice300 import LAYOUTS, SEED, VERSION, all_cases
from scripts.check_invoice300_acceptance import evaluate_reports, main


def synthetic_reports():
    """Build consistent benchmark-shaped partitions at the documented baseline."""
    cases = all_cases()
    reports = []
    manifest_path = Path(__file__).resolve().parents[1] / "scripts/baselines/invoice300_paddle_v1.json"
    historical = json.loads(manifest_path.read_text(encoding="utf-8"))["cases"]
    for shard in range(6):
        rows = []
        for idx, case in enumerate(cases):
            if idx % 6 != shard:
                continue
            layout = case["layout"]
            total = 3 + 4 * len(case["rows"])
            prior = historical[case["id"]]
            extra = prior["extra_item_rows"]
            self_flags = [bit == "1" for bit in prior["correct"]]
            fields = ["patient.name", "invoice.number", "invoice.total"]
            for n in range(1, len(case["rows"]) + 1):
                fields.extend(f"item.{n}.{key}" for key in ("name", "qty", "price", "total"))
            checks = [{"field": name, "matched": flag, "linked_evidence": flag}
                      for name, flag in zip(fields, self_flags)]
            matched = sum(self_flags)
            matched_names = sum(ch["matched"] and re.fullmatch(r"item\.\d+\.name", ch["field"]) is not None
                                for ch in checks)
            rows.append({
                "case": case["id"], "layout": layout, "model": "paddle_arabic",
                "matched": matched, "total": total, "with_evidence": matched,
                "expected_item_rows": len(case["rows"]),
                "matched_item_names": matched_names,
                "extracted_item_rows": matched_names + extra,
                "extra_item_rows": extra, "real_paddle_detected": True,
                "review_required": True, "page_failures": [], "checks": checks,
            })
        reports.append({
            "status": "completed_real_ocr", "seed": SEED, "version": VERSION,
            "shard": shard, "shards": 6, "cases": 50, "engines": ["paddle_arabic"],
            "failure_records": [], "results": rows,
        })
    # Distribution above is intentionally artificial; recompute all summaries.
    for report in reports:
        refresh(report)
    return reports


def refresh(report):
    rows = report["results"]
    report["summary"] = {"paddle_arabic": {
        "documents": len(rows), "matched": sum(r["matched"] for r in rows),
        "expected": sum(r["total"] for r in rows),
        "evidence": sum(r["with_evidence"] for r in rows),
        "expected_items": sum(r["expected_item_rows"] for r in rows),
        "matched_item_names": sum(r["matched_item_names"] for r in rows),
        "extra_item_rows": sum(r["extra_item_rows"] for r in rows),
        "failures": 0,
    }}
    by_layout = defaultdict(dict)
    for layout in LAYOUTS:
        subset = [r for r in rows if r["layout"] == layout]
        by_layout[layout]["paddle_arabic"] = {
            "matched": sum(r["matched"] for r in subset),
            "expected": sum(r["total"] for r in subset),
            "evidence": sum(r["with_evidence"] for r in subset),
            "docs": len(subset),
        }
    report["by_layout"] = dict(by_layout)


def recount(row):
    row["matched"] = sum(ch["matched"] for ch in row["checks"])
    row["with_evidence"] = sum(ch["linked_evidence"] for ch in row["checks"])
    row["matched_item_names"] = sum(
        ch["matched"] and re.fullmatch(r"item\.\d+\.name", ch["field"]) is not None
        for ch in row["checks"])
    row["extracted_item_rows"] = row["matched_item_names"] + row["extra_item_rows"]


class Invoice300Acceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = synthetic_reports()

    def test_unchanged_baseline_passes_with_exact_300_cases(self):
        decision = evaluate_reports(self.baseline)
        self.assertEqual(decision["status"], "PASS", decision["reasons"])
        self.assertEqual(decision["totals"]["matched"], 4895)
        self.assertEqual(decision["totals"]["expected"], 5776)
        self.assertEqual(decision["totals"]["extra_item_rows"], 99)
        self.assertEqual(decision["dataset"]["documents"], 300)
        self.assertFalse(decision["production_ready"])

    def test_any_layout_field_regression_is_blocked(self):
        reports = copy.deepcopy(self.baseline)
        row = next(r for rep in reports for r in rep["results"]
                   if r["layout"] == "ar_mixed" and r["matched"] > 0)
        check = next(c for c in row["checks"] if c["matched"] and c["field"] != "item.1.name")
        check["matched"] = False
        check["linked_evidence"] = False
        recount(row)
        for rep in reports:
            refresh(rep)
        d = evaluate_reports(reports)
        self.assertEqual(d["status"], "BLOCKED")
        self.assertTrue(any("ar_mixed" in reason for reason in d["reasons"]))

    def test_offsetting_gains_cannot_hide_a_lost_correct_field(self):
        reports = copy.deepcopy(self.baseline)
        rows = [r for rep in reports for r in rep["results"] if r["layout"] == "ar_mixed"]
        old_row = next(r for r in rows if any(c["matched"] for c in r["checks"]))
        new_row = next(r for r in rows if any(not c["matched"] for c in r["checks"]))
        old_check = next(c for c in old_row["checks"] if c["matched"])
        new_check = next(c for c in new_row["checks"] if not c["matched"])
        old_check["matched"] = old_check["linked_evidence"] = False
        new_check["matched"] = new_check["linked_evidence"] = True
        recount(old_row)
        recount(new_row)
        for rep in reports:
            refresh(rep)
        decision = evaluate_reports(reports)
        self.assertEqual(decision["totals"]["matched"], 4895)
        self.assertEqual(decision["status"], "BLOCKED")
        self.assertTrue(any("previously correct field" in x for x in decision["reasons"]))

    def test_one_added_false_row_is_blocked(self):
        reports = copy.deepcopy(self.baseline)
        row = next(r for rep in reports for r in rep["results"] if r["layout"] == "en_standard")
        row["extracted_item_rows"] += 1
        row["extra_item_rows"] += 1
        for rep in reports:
            refresh(rep)
        d = evaluate_reports(reports)
        self.assertEqual(d["status"], "BLOCKED")
        self.assertTrue(any("en_standard" in reason for reason in d["reasons"]))

    def test_missing_shard_is_blocked(self):
        d = evaluate_reports(self.baseline[:5])
        self.assertEqual(d["status"], "BLOCKED")

    def test_duplicate_or_replaced_case_is_blocked(self):
        reports = copy.deepcopy(self.baseline)
        reports[0]["results"][0]["case"] = reports[0]["results"][1]["case"]
        d = evaluate_reports(reports)
        self.assertEqual(d["status"], "BLOCKED")

    def test_wrong_seed_and_version_are_blocked(self):
        for key, bad in (("seed", 0), ("version", "other")):
            reports = copy.deepcopy(self.baseline)
            reports[0][key] = bad
            self.assertEqual(evaluate_reports(reports)["status"], "BLOCKED", key)

    def test_real_engine_and_human_review_are_mandatory(self):
        for key in ("real_paddle_detected", "review_required"):
            reports = copy.deepcopy(self.baseline)
            reports[0]["results"][0][key] = False
            self.assertEqual(evaluate_reports(reports)["status"], "BLOCKED", key)

    def test_summary_disagreement_blocks(self):
        reports = copy.deepcopy(self.baseline)
        reports[2]["summary"]["paddle_arabic"]["matched"] += 1
        self.assertEqual(evaluate_reports(reports)["status"], "BLOCKED")

    def test_field_checks_cannot_claim_unlinked_matching_evidence(self):
        reports = copy.deepcopy(self.baseline)
        reports[1]["results"][0]["checks"][0]["linked_evidence"] = False
        self.assertEqual(evaluate_reports(reports)["status"], "BLOCKED")

    def test_cli_exit_code_and_privacy_safe_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = []
            for index, report in enumerate(self.baseline):
                path = Path(temp_dir) / f"shard{index}.json"
                path.write_text(json.dumps(report), encoding="utf-8")
                paths.append(str(path))
            out = io.StringIO()
            with redirect_stdout(out):
                exit_code = main(paths[::-1])
            decision = json.loads(out.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(decision["status"], "PASS")
            self.assertNotIn("Test Person", out.getvalue())
            out = io.StringIO()
            with redirect_stdout(out):
                exit_code = main(paths[:-1])
            self.assertEqual(exit_code, 1)
            self.assertEqual(json.loads(out.getvalue())["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
