"""Freeze only score flags from an audited 300-invoice synthetic OCR run.

This is a maintainer-only baseline update helper. Changing a tracked baseline
requires explicit owner approval; normal release checks never call this file.
No OCR text, patient name, amount, or PDF is copied into the compact manifest.
"""
import argparse
import json
from pathlib import Path

from scripts.check_invoice300_acceptance import ENGINE, SEED, VERSION, evaluate_reports


def freeze(reports, run_id):
    decision = evaluate_reports(reports)
    if decision["status"] != "PASS":
        raise ValueError("only a complete previously accepted synthetic run can be frozen")
    cases = {}
    for report in reports:
        for row in report["results"]:
            cases[row["case"]] = {
                "correct": "".join("1" if c["matched"] else "0" for c in row["checks"]),
                "extra_item_rows": row["extra_item_rows"],
            }
    return {
        "purpose": "Historic correct-field preservation; NOT proof of clinical accuracy",
        "source_github_actions_run_id": run_id,
        "seed": SEED, "version": VERSION, "engine": ENGINE,
        "documents": 300, "matched": decision["totals"]["matched"],
        "expected": decision["totals"]["expected"],
        "extra_item_rows": decision["totals"]["extra_item_rows"],
        "cases": dict(sorted(cases.items())),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run-id", required=True, type=int)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("reports", nargs=6, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("baseline exists; changing it requires separate owner approval")
    reports = [json.loads(p.read_text(encoding="utf-8")) for p in args.reports]
    manifest = freeze(reports, args.source_run_id)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Frozen {manifest['documents']} synthetic cases from run {args.source_run_id}")


if __name__ == "__main__":
    main()
