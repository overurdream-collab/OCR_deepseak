"""Combine complete benchmark shards; completion is distinct from 100% acceptance."""
import argparse
import json
from collections import Counter
from pathlib import Path

from scripts.benchmark_invoice300 import VERSION, SEED, all_cases


def summarize(reports, engine="paddle_arabic"):
    expected = {c["id"]: {"patient.name", "invoice.number", "invoice.total"} |
                {f"item.{i}.{key}" for i in range(1, len(c["rows"]) + 1)
                 for key in ("name", "qty", "price", "total")}
                for c in all_cases()}
    records = {}
    for report in reports:
        if (report.get("status") != "completed_real_ocr"
                or report.get("version") != VERSION or report.get("seed") != SEED):
            raise ValueError("Incomplete or incompatible benchmark report")
        for row in report.get("results", []):
            if row.get("model") != engine:
                continue
            case = row.get("case")
            if case in records or case not in expected:
                raise ValueError(f"Duplicate or unknown case: {case}")
            checks = row.get("checks", [])
            if (len(checks) != len(expected[case])
                    or {x["field"] for x in checks} != expected[case]):
                raise ValueError(f"Missing or duplicate field checks: {case}")
            records[case] = row
    if set(records) != set(expected):
        raise ValueError(f"Expected all 300 invoices, received {len(records)}")
    errors, by_layout = Counter(), {}
    matched = evidence = extra = failures = 0
    for row in records.values():
        checks = row["checks"]
        correct = sum(x["matched"] is True for x in checks)
        matched += correct
        evidence += sum(x["matched"] is True and x["linked_evidence"] is True for x in checks)
        extra += row["extra_item_rows"]
        failures += bool(row.get("runtime_error") or row.get("page_failures")
                         or (engine.startswith("paddle_arabic") and not row.get("real_paddle_detected")))
        layout = by_layout.setdefault(row["layout"], {"documents": 0, "correct": 0, "expected": 0})
        layout["documents"] += 1
        layout["correct"] += correct
        layout["expected"] += len(checks)
        for check in checks:
            if check["matched"] is not True:
                field = check["field"].split(".")
                errors["item." + field[-1] if field[0] == "item" else check["field"]] += 1
    total = sum(map(len, expected.values()))
    return {"documents": len(records), "correct": matched, "expected": total,
            "field_accuracy": matched / total, "with_evidence": evidence,
            "extra_item_rows": extra, "failures": failures,
            "accepted_100_percent": matched == total and evidence == total and extra == 0 and failures == 0,
            "errors_by_field": dict(errors), "by_layout": by_layout}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", type=Path, nargs="+")
    parser.add_argument("--engine", default="paddle_arabic")
    parser.add_argument("--require-perfect", action="store_true")
    args = parser.parse_args()
    result = summarize([json.loads(p.read_text("utf-8")) for p in args.reports], args.engine)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.require_perfect and not result["accepted_100_percent"]:
        raise SystemExit(1)
