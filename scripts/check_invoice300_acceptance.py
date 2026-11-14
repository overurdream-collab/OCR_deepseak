"""Fail-closed release gate for six real PaddleOCR synthetic-invoice score reports.

This script NEVER performs OCR, reads PDFs, or modifies a medical/financial value.
It requires the complete frozen 300-case benchmark and checks for regressions in
each layout separately. PASS only means synthetic-benchmark non-regression.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


ENGINE = "paddle_arabic"
SEED = 20261026
VERSION = "SYNTHETIC-INVOICE-300-HOLDOUT-v1"
BASELINE = {
    "en_standard": {"matched": 910, "expected": 942, "extra_item_rows": 3},
    "en_reordered": {"matched": 927, "expected": 970, "extra_item_rows": 5},
    "en_compact": {"matched": 921, "expected": 958, "extra_item_rows": 4},
    "ar_shaped": {"matched": 758, "expected": 1018, "extra_item_rows": 30},
    "ar_visual": {"matched": 710, "expected": 930, "extra_item_rows": 20},
    "ar_mixed": {"matched": 669, "expected": 958, "extra_item_rows": 37},
}
FROZEN_BASELINE = Path(__file__).resolve().parent / "baselines" / "invoice300_paddle_v1.json"
EXPECTED_CASES = {
    f"{layout}_{index:02d}": (layout, offset % 6)
    for offset, (layout, index) in enumerate(
        (layout, index) for layout in BASELINE for index in range(10, 60)
    )
}
_NAME_FIELD = re.compile(r"item\.\d+\.name\Z")


class InvalidReport(ValueError):
    """A report cannot prove its own completeness or correctness."""


def _integer(obj, key):
    value = obj.get(key)
    if type(value) is not int or value < 0:
        raise InvalidReport(f"{key}: expected a nonnegative integer")
    return value


def _equal(actual, expected, label):
    if actual != expected:
        raise InvalidReport(f"{label}: inconsistent or unexpected value")


def _count_fields(record):
    checks = record.get("checks")
    if not isinstance(checks, list):
        raise InvalidReport("checks: missing field-level evidence")
    expected_fields = ["patient.name", "invoice.number", "invoice.total"]
    for index in range(1, _integer(record, "expected_item_rows") + 1):
        expected_fields.extend(f"item.{index}.{name}" for name in
                               ("name", "qty", "price", "total"))
    _equal(len(checks), len(expected_fields), "checks field count")
    if [c.get("field") if isinstance(c, dict) else None for c in checks] != expected_fields:
        raise InvalidReport("checks: field names/order do not match printed item count")
    matched = evidence = matched_names = 0
    for check in checks:
        if type(check.get("matched")) is not bool or type(check.get("linked_evidence")) is not bool:
            raise InvalidReport("checks: matched/evidence must be booleans")
        if check["linked_evidence"] and not check["matched"]:
            raise InvalidReport("checks: evidence cannot support an unmatched value")
        matched += check["matched"]
        evidence += check["linked_evidence"]
        if check["matched"] and _NAME_FIELD.fullmatch(check["field"]):
            matched_names += 1
    return matched, evidence, matched_names, len(checks)


def _validate_case(record, shard):
    if not isinstance(record, dict):
        raise InvalidReport("case: expected object")
    case_id = record.get("case")
    if case_id not in EXPECTED_CASES:
        raise InvalidReport("case: unknown synthetic benchmark ID")
    layout, expected_shard = EXPECTED_CASES[case_id]
    _equal(record.get("layout"), layout, "case layout")
    _equal(shard, expected_shard, "case partition")
    _equal(record.get("model"), ENGINE, "case engine")
    if record.get("real_paddle_detected") is not True:
        raise InvalidReport("case: actual PaddleOCR execution not proven")
    if record.get("review_required") is not True:
        raise InvalidReport("case: human-review protection missing")
    if record.get("runtime_error") or record.get("page_failures") != []:
        raise InvalidReport("case: OCR runtime/page failure")
    matched, evidence, names, total = _count_fields(record)
    for key, actual in (("matched", matched), ("with_evidence", evidence),
                        ("matched_item_names", names), ("total", total)):
        _equal(_integer(record, key), actual, f"case {key}")
    printed = _integer(record, "expected_item_rows")
    extracted = _integer(record, "extracted_item_rows")
    _equal(_integer(record, "extra_item_rows"), max(0, extracted - names),
           "case extra_item_rows")
    if names > printed:
        raise InvalidReport("case: impossible number of matched service names")
    return case_id, layout


def _stats(rows):
    return {
        "documents": len(rows),
        "matched": sum(row["matched"] for row in rows),
        "expected": sum(row["total"] for row in rows),
        "evidence": sum(row["with_evidence"] for row in rows),
        "expected_items": sum(row["expected_item_rows"] for row in rows),
        "matched_item_names": sum(row["matched_item_names"] for row in rows),
        "extra_item_rows": sum(row["extra_item_rows"] for row in rows),
        "failures": 0,
    }


def _validate_partition(report):
    if not isinstance(report, dict):
        raise InvalidReport("partition: expected JSON object")
    shard = _integer(report, "shard")
    if shard >= 6:
        raise InvalidReport("partition: shard ID out of range")
    for key, expected in (("status", "completed_real_ocr"), ("seed", SEED),
                          ("version", VERSION), ("shards", 6), ("cases", 50),
                          ("engines", [ENGINE]), ("failure_records", [])):
        _equal(report.get(key), expected, f"partition {key}")
    rows = report.get("results")
    if not isinstance(rows, list) or len(rows) != 50:
        raise InvalidReport("partition: expected exactly 50 detailed case scores")
    case_ids = set()
    for row in rows:
        case_id, _ = _validate_case(row, shard)
        if case_id in case_ids:
            raise InvalidReport("partition: duplicate synthetic case ID")
        case_ids.add(case_id)
    expected_ids = {case for case, (_, partition) in EXPECTED_CASES.items()
                    if partition == shard}
    if case_ids != expected_ids:
        raise InvalidReport("partition: missing or unexpected synthetic case IDs")
    summary = (report.get("summary") or {}).get(ENGINE)
    if not isinstance(summary, dict):
        raise InvalidReport("partition: engine summary missing")
    for key, expected in _stats(rows).items():
        _equal(_integer(summary, key), expected, f"partition summary.{key}")
    layout_reports = report.get("by_layout")
    if not isinstance(layout_reports, dict):
        raise InvalidReport("partition: layout summaries missing")
    for layout in BASELINE:
        subset = [r for r in rows if r["layout"] == layout]
        one_layout = (layout_reports.get(layout) or {}).get(ENGINE)
        if not isinstance(one_layout, dict):
            raise InvalidReport("partition: layout summary missing")
        for key, expected in (("matched", sum(r["matched"] for r in subset)),
                              ("expected", sum(r["total"] for r in subset)),
                              ("evidence", sum(r["with_evidence"] for r in subset)),
                              ("docs", len(subset))):
            _equal(_integer(one_layout, key), expected, f"partition layout.{layout}.{key}")
    return shard, rows


def _frozen_case_baseline():
    """Load audited correct-field bitsets, independent of the candidate reports."""
    try:
        manifest = json.loads(FROZEN_BASELINE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidReport(f"frozen baseline unavailable ({type(exc).__name__})") from exc
    if not isinstance(manifest, dict):
        raise InvalidReport("frozen baseline: invalid manifest")
    for key, expected in (("seed", SEED), ("version", VERSION), ("engine", ENGINE),
                          ("documents", 300), ("matched", 4895), ("expected", 5776),
                          ("extra_item_rows", 99), ("source_github_actions_run_id", 40180808910)):
        _equal(manifest.get(key), expected, f"frozen baseline {key}")
    cases = manifest.get("cases")
    if not isinstance(cases, dict) or set(cases) != set(EXPECTED_CASES):
        raise InvalidReport("frozen baseline: incomplete case identity map")
    fields = correct = extras = 0
    for case in cases.values():
        if not isinstance(case, dict) or not isinstance(case.get("correct"), str):
            raise InvalidReport("frozen baseline: invalid correctness mask")
        bits = case["correct"]
        if not bits or any(bit not in "01" for bit in bits):
            raise InvalidReport("frozen baseline: malformed correctness mask")
        fields += len(bits)
        correct += bits.count("1")
        extras += _integer(case, "extra_item_rows")
    _equal((fields, correct, extras), (5776, 4895, 99), "frozen baseline counters")
    return cases


def evaluate_reports(reports):
    """Return a privacy-safe decision for parsed JSON report dictionaries."""
    errors = []
    partitions = {}
    if len(reports) != 6:
        errors.append(f"expected 6 shard reports; received {len(reports)}")
    for index, report in enumerate(reports):
        try:
            shard, rows = _validate_partition(report)
            if shard in partitions:
                raise InvalidReport("duplicate shard ID")
            partitions[shard] = rows
        except (InvalidReport, TypeError, KeyError, AttributeError) as exc:
            errors.append(f"report {index + 1}: {exc}")
    if set(partitions) != set(range(6)):
        errors.append("missing valid shard IDs: " +
                      ", ".join(str(i) for i in sorted(set(range(6)) - set(partitions))))
    grouped = defaultdict(list)
    for rows in partitions.values():
        for record in rows:
            grouped[record["layout"]].append(record)
    try:
        frozen_cases = _frozen_case_baseline()
    except (InvalidReport, TypeError, AttributeError) as exc:
        errors.append(str(exc))
        frozen_cases = {}
    for rows in partitions.values():
        for record in rows:
            previous = frozen_cases.get(record["case"])
            if previous is None:
                continue
            old_flags = previous["correct"]
            current_flags = [check["matched"] for check in record["checks"]]
            if len(old_flags) != len(current_flags):
                errors.append(f"{record['case']}: historical field count changed")
            elif any(bit == "1" and not observed for bit, observed in zip(old_flags, current_flags)):
                errors.append(f"{record['case']}: previously correct field was lost")
            if record["extra_item_rows"] > previous["extra_item_rows"]:
                errors.append(f"{record['case']}: added false rows compared with historical case")
    by_layout = {}
    for layout, base in BASELINE.items():
        rows = grouped[layout]
        observed = {
            "documents": len(rows),
            "matched": sum(r["matched"] for r in rows),
            "expected": sum(r["total"] for r in rows),
            "extra_item_rows": sum(r["extra_item_rows"] for r in rows),
        }
        observed["accuracy_percent"] = round(100 * observed["matched"] / observed["expected"], 2) if observed["expected"] else 0
        observed["baseline"] = dict(base)
        observed["matched_delta"] = observed["matched"] - base["matched"]
        observed["extra_rows_delta"] = observed["extra_item_rows"] - base["extra_item_rows"]
        by_layout[layout] = observed
        if observed["documents"] != 50:
            errors.append(f"{layout}: expected 50 documents; found {observed['documents']}")
        if observed["expected"] != base["expected"]:
            errors.append(f"{layout}: expected-field denominator changed")
        if observed["matched"] < base["matched"]:
            errors.append(f"{layout}: matched {observed['matched']} < baseline {base['matched']}")
        if observed["extra_item_rows"] > base["extra_item_rows"]:
            errors.append(f"{layout}: extra rows {observed['extra_item_rows']} > baseline {base['extra_item_rows']}")
    totals = {
        "documents": sum(x["documents"] for x in by_layout.values()),
        "matched": sum(x["matched"] for x in by_layout.values()),
        "expected": sum(x["expected"] for x in by_layout.values()),
        "extra_item_rows": sum(x["extra_item_rows"] for x in by_layout.values()),
        "failures": 0 if not errors else None,
    }
    totals["accuracy_percent"] = round(100 * totals["matched"] / totals["expected"], 2) if totals["expected"] else 0
    return {
        "status": "BLOCKED" if errors else "PASS",
        "synthetic_only": True,
        "production_ready": False,
        "dataset": {"seed": SEED, "version": VERSION, "engine": ENGINE,
                    "documents": totals["documents"], "expected_documents": 300},
        "totals": totals,
        "by_layout": by_layout,
        "reasons": errors,
    }


def main(argv=None):
    paths = list(sys.argv[1:] if argv is None else argv)
    reports, failures = [], []
    for index, path in enumerate(paths):
        try:
            reports.append(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            reports.append({})
            failures.append(f"report {index + 1}: unavailable or invalid JSON ({type(exc).__name__})")
    result = evaluate_reports(reports)
    if failures:
        result["reasons"] = failures + result["reasons"]
        result["status"] = "BLOCKED"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
