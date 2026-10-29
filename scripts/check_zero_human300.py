"""Strict, independent zero-human 300-PDF safety gate.

0 referrals does not mean 0 unreadable fields. Any unresolved field MUST
remain blocked. Compare every synthetic correctness bit against frozen PR24
95.29% source-Paddle benchmark, no previously correct fields lost.
"""
import argparse
import json
from pathlib import Path

from scripts.compare_ambiguous_rows300 import compare


def verify_no_human(paths):
    cases = []
    for path in paths:
        report = json.loads(Path(path).read_text("utf-8"))
        if report.get("status") != "completed_real_ocr":
            raise ValueError("partial real-OCR shard")
        if report.get("engines") != ["paddle_arabic"]:
            raise ValueError("wrong OCR engine")
        cases.extend(report["results"])
    if len(cases) != 300 or len({c["case"] for c in cases}) != 300:
        raise ValueError("exactly 300 unique original invoice PDFs required")
    count_blocked = 0
    for c in cases:
        if c.get("runtime_error") or c.get("page_failures"):
            raise ValueError("OCR runtime failure " + c["case"])
        if not c.get("real_paddle_detected"):
            raise ValueError("PaddleOCR not actually used " + c["case"])
        if c.get("automation_policy") != "zero_human_fail_closed":
            raise ValueError("zero-human mode missing " + c["case"])
        if c.get("review_required") is not False or c.get("human_handoffs") != 0:
            raise ValueError("nonzero human referral " + c["case"])
        if c.get("financial_approval") is not False:
            raise ValueError("medical money automatically approved " + c["case"])
        m = c.get("machine_unresolved_count")
        if type(m) is not int or m < 0:
            raise ValueError("machine blocker ledger missing " + c["case"])
        if c.get("extraction_ready") is not (m == 0):
            raise ValueError("unresolved document incorrectly marked ready " + c["case"])
        status = "completed" if m == 0 else "blocked_unresolved"
        if c.get("status") != status or c.get("original_extraction_status") != status:
            raise ValueError("blocked status mismatch " + c["case"])
        count_blocked += m > 0
    return {"documents": len(cases), "human_handoffs": 0,
            "unresolved_documents_blocked": count_blocked,
            "documents_ready": len(cases) - count_blocked,
            "total_machine_unresolved_checks": sum(c["machine_unresolved_count"] for c in cases)}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--previous",nargs=6,required=True)
    p.add_argument("--current",nargs=6,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    routing=verify_no_human(a.current)
    old_vs_new=compare(a.previous,a.current)
    if old_vs_new["status"]!="PASS":
        raise ValueError("regression against last verified source OCR accuracy")
    report={"status":"PASS","routing":routing,
            "accuracy":{"baseline_correct":old_vs_new["baseline"],
                        "candidate_correct":old_vs_new["candidate"],
                        "expected_fields":old_vs_new["total"],
                        "gained":old_vs_new["gained"],
                        "lost":old_vs_new["lost"],
                        "new_extra_rows":old_vs_new["new_extra_rows"]}}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",
                        encoding="utf-8")
    print(json.dumps({**routing,"baseline":old_vs_new["baseline"],
                      "correct":old_vs_new["candidate"],
                      "lost":len(old_vs_new["lost"]),"new_extra_rows":len(old_vs_new["new_extra_rows"])},
                     ensure_ascii=False))


if __name__=="__main__":
    main()
