"""Compare full, truth-linked 300-invoice OCR runs without rewriting any field.

This is an *evaluation* tool, not a runtime OCR fusion algorithm.  An oracle
which knew every expected answer could pick the right engine per field, but
MDIA has no such oracle when processing a real patient's invoice.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from scripts.check_invoice300_acceptance import (EXPECTED_CASES, SEED, VERSION,
                                                  InvalidReport, _count_fields)


_FINANCIAL = re.compile(r"(?:invoice\.total|item\.\d+\.(?:qty|price|total))\Z")


def _require(condition, message):
    if not condition:
        raise InvalidReport(message)


def load_run(paths, engine):
    """Require a complete, internally consistent 300-case real-OCR run."""
    paths = list(paths)
    _require(len(paths) == 6, f"{engine}: expected exactly six shard files")
    by_case, shards = {}, set()
    for path in paths:
        try:
            report = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise InvalidReport(f"{engine}: unreadable report ({type(exc).__name__})") from exc
        _require(isinstance(report, dict), f"{engine}: invalid report object")
        shard = report.get("shard")
        _require(type(shard) is int and 0 <= shard < 6 and shard not in shards,
                 f"{engine}: duplicate/invalid shard")
        shards.add(shard)
        for key, expected in (("seed", SEED), ("version", VERSION),
                              ("status", "completed_real_ocr"), ("cases", 50),
                              ("shards", 6), ("engines", [engine]),
                              ("failure_records", [])):
            _require(report.get(key) == expected, f"{engine}: wrong {key} in shard {shard}")
        rows = report.get("results")
        _require(isinstance(rows, list) and len(rows) == 50,
                 f"{engine}: shard {shard} lacks 50 detailed cases")
        for row in rows:
            _require(isinstance(row, dict), f"{engine}: malformed case")
            case_id = row.get("case")
            _require(case_id in EXPECTED_CASES and case_id not in by_case,
                     f"{engine}: unexpected/duplicate case {case_id}")
            layout, partition = EXPECTED_CASES[case_id]
            _require(partition == shard and row.get("layout") == layout and
                     row.get("model") == engine, f"{engine}: case identity mismatch")
            _require(row.get("real_paddle_detected") is (engine == "paddle_arabic"),
                     f"{engine}: engine proof mismatch at {case_id}")
            _require(type(row.get("review_required")) is bool,
                     f"{engine}: missing review state at {case_id}")
            _require(row.get("page_failures") == [] and not row.get("runtime_error"),
                     f"{engine}: page/OCR failure at {case_id}")
            matched, evidence, names, total = _count_fields(row)
            for key, expected in (("matched", matched), ("with_evidence", evidence),
                                  ("matched_item_names", names), ("total", total)):
                _require(type(row.get(key)) is int and row[key] == expected,
                         f"{engine}: inconsistent {key} at {case_id}")
            expected_rows, extracted_rows, extra_rows = (
                row.get("expected_item_rows"), row.get("extracted_item_rows"),
                row.get("extra_item_rows"))
            _require(all(type(v) is int and v >= 0 for v in
                         (expected_rows, extracted_rows, extra_rows)) and
                     extra_rows == max(0, extracted_rows - names),
                     f"{engine}: invalid row accounting at {case_id}")
            by_case[case_id] = row
        summary = (report.get("summary") or {}).get(engine)
        _require(isinstance(summary, dict), f"{engine}: missing shard summary")
        for key, expected in (("documents", 50),
                              ("matched", sum(r["matched"] for r in rows)),
                              ("expected", sum(r["total"] for r in rows)),
                              ("extra_item_rows", sum(r["extra_item_rows"] for r in rows)),
                              ("failures", 0)):
            _require(type(summary.get(key)) is int and summary[key] == expected,
                     f"{engine}: invalid summary.{key} in shard {shard}")
    _require(set(by_case) == set(EXPECTED_CASES) and shards == set(range(6)),
             f"{engine}: missing benchmark cases or shards")
    return by_case


def compare_runs(primary, candidate, primary_label="PaddleOCR",
                 candidate_label="Tesseract Best"):
    """Return exact-match gains/losses and a *non-deployable* oracle ceiling."""
    _require(set(primary) == set(candidate) == set(EXPECTED_CASES),
             "incomplete or nonidentical case IDs")
    counts = defaultdict(lambda: defaultdict(int))
    changed_cases, regressions, review_regressions, financial_losses = set(), set(), set(), 0
    for case_id in sorted(primary):
        pr, cr = primary[case_id], candidate[case_id]
        _require(pr["layout"] == cr["layout"], f"layout mismatch at {case_id}")
        layout = pr["layout"]
        _require(pr["expected_item_rows"] == cr["expected_item_rows"],
                 f"printed row count mismatch at {case_id}")
        pchecks, cchecks = pr["checks"], cr["checks"]
        _require(len(pchecks) == len(cchecks), f"field count mismatch at {case_id}")
        counts[layout]["documents"] += 1
        counts[layout]["primary_extra_rows"] += pr["extra_item_rows"]
        counts[layout]["candidate_extra_rows"] += cr["extra_item_rows"]
        counts[layout]["primary_unreviewed_documents"] += not bool(pr["review_required"])
        counts[layout]["candidate_unreviewed_documents"] += not bool(cr["review_required"])
        if pr["review_required"] and not cr["review_required"]:
            review_regressions.add(case_id)
        if cr["extra_item_rows"] > pr["extra_item_rows"]:
            regressions.add(case_id)
        for p, c in zip(pchecks, cchecks):
            _require(p["field"] == c["field"] and p["expected"] == c["expected"],
                     f"unaligned ground truth at {case_id}: {p['field']}")
            po, co = p["matched"], c["matched"]
            _require(type(po) is bool and type(co) is bool,
                     f"invalid correctness flags at {case_id}")
            counts[layout]["fields"] += 1
            counts[layout]["primary_correct"] += po
            counts[layout]["candidate_correct"] += co
            counts[layout]["oracle_correct"] += po or co
            counts[layout]["candidate_only_correct"] += co and not po
            counts[layout]["primary_only_correct"] += po and not co
            counts[layout]["both_wrong"] += not (po or co)
            if po != co:
                changed_cases.add(case_id)
            if po and not co:
                regressions.add(case_id)
                financial_losses += bool(_FINANCIAL.fullmatch(p["field"]))

    by_layout = dict(sorted((layout, dict(stats)) for layout, stats in counts.items()))
    totals = {key: sum(v.get(key, 0) for v in by_layout.values()) for key in (
        "documents", "fields", "primary_correct", "candidate_correct", "oracle_correct",
        "candidate_only_correct", "primary_only_correct", "both_wrong",
        "primary_extra_rows", "candidate_extra_rows",
        "primary_unreviewed_documents", "candidate_unreviewed_documents")}
    totals["primary_accuracy_percent"] = round(totals["primary_correct"] / totals["fields"] * 100, 2)
    totals["candidate_accuracy_percent"] = round(totals["candidate_correct"] / totals["fields"] * 100, 2)
    totals["oracle_upper_bound_percent"] = round(totals["oracle_correct"] / totals["fields"] * 100, 2)
    return {
        "status": "BLOCKED_FOR_AUTOMATIC_REPLACEMENT" if regressions or review_regressions
                  else "NONREGRESSION_PASS",
        "synthetic_only": True,
        "oracle_is_not_deployable": True,
        "primary": primary_label,
        "candidate": candidate_label,
        "totals": totals,
        "financial_fields_lost_by_candidate": financial_losses,
        "changed_case_count": len(changed_cases),
        "regressed_case_count": len(regressions),
        "review_regression_case_count": len(review_regressions),
        "by_layout": by_layout,
        "recommendation": "review_only_second_opinion" if totals["candidate_only_correct"] else
                          "no_verified_candidate_gain",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", nargs=6, required=True, metavar="JSON")
    parser.add_argument("--candidate", nargs=6, required=True, metavar="JSON")
    parser.add_argument("--primary-engine", default="paddle_arabic")
    parser.add_argument("--candidate-engine", default="tesseract")
    parser.add_argument("--candidate-label", default="Tesseract Best (ara+eng)")
    parser.add_argument("--output", type=Path, help="Write the complete evaluation JSON here")
    parser.add_argument("--fail-on-regression", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = compare_runs(load_run(args.primary, args.primary_engine),
                              load_run(args.candidate, args.candidate_engine),
                              primary_label=args.primary_engine,
                              candidate_label=args.candidate_label)
    except (InvalidReport, KeyError, AttributeError, TypeError) as exc:
        print(json.dumps({"status": "INVALID_REPORT", "reason": str(exc)}), file=sys.stderr)
        return 2
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return int(args.fail_on_regression and result["status"] != "NONREGRESSION_PASS")


if __name__ == "__main__":
    raise SystemExit(main())
