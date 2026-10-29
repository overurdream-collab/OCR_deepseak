"""Absolute release gate: no referrals are acceptable only with zero errors.

Checks all 300 actual PaddleOCR synthetic invoices and every expected field.
Zero routing or an unresolved ledger cannot turn an incorrect field into PASS.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ENGINE="paddle_arabic"
SEED=20261026
VERSION="SYNTHETIC-INVOICE-300-HOLDOUT-v1"
LAYOUTS=("en_standard","en_reordered","en_compact","ar_shaped","ar_visual","ar_mixed")
EXPECTED={f"{layout}_{n:02d}" for layout in LAYOUTS for n in range(10,60)}


def evaluate_reports(reports):
    seen=set()
    total=correct=extra=evidence_gaps=human_docs=failed_pages=0
    missing,wrong=Counter(),Counter()
    for report in reports:
        if (report.get("status")!="completed_real_ocr" or
            report.get("seed")!=SEED or report.get("version")!=VERSION or
            report.get("engines")!=[ENGINE] or report.get("failure_records")):
            raise ValueError("incomplete or non-Paddle original-PDF OCR report")
        for rec in report.get("results") or ():
            case=rec.get("case")
            if case not in EXPECTED or case in seen:
                raise ValueError("invalid or duplicate test case "+str(case))
            seen.add(case)
            if not rec.get("real_paddle_detected") or rec.get("page_failures") or rec.get("runtime_error"):
                failed_pages+=1
            if rec.get("review_required") is not False or rec.get("human_handoffs",0)!=0:
                human_docs+=1
            extra+=rec.get("extra_item_rows",0)
            checks=rec.get("checks")
            if not isinstance(checks,list) or len(checks)!=rec.get("total"):
                raise ValueError("incomplete field checks for "+case)
            total+=len(checks)
            one=sum(x.get("matched") is True for x in checks)
            if rec.get("matched")!=one:
                raise ValueError("inconsistent accuracy counts "+case)
            correct+=one
            for check in checks:
                if check.get("matched") is True:
                    if check.get("linked_evidence") is not True:
                        evidence_gaps+=1
                else:
                    field=check.get("field","unknown")
                    group=("patient.name" if field=="patient.name" else
                           field if field.startswith("invoice.") else field.split(".")[-1])
                    (missing if check.get("actual") is None else wrong)[group]+=1
    if seen!=EXPECTED:
        raise ValueError("not all frozen 300 invoices were evaluated")
    passed=(total==5776 and correct==total and extra==0
            and human_docs==0 and evidence_gaps==0 and failed_pages==0)
    return {
        "status":"PASS" if passed else "BLOCKED",
        "documents":len(seen),"correct":correct,"expected":total,
        "errors_or_missing":total-correct,"spurious_rows":extra,
        "human_referral_documents":human_docs,"evidence_gaps":evidence_gaps,
        "failed_pages":failed_pages,
        "missing_by_field":dict(sorted(missing.items())),
        "incorrect_by_field":dict(sorted(wrong.items())),
        "acceptance":"5776/5776 exact with linked evidence, zero missing/wrong, zero extra rows, zero referrals"
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("reports",nargs="+",type=Path)
    p.add_argument("--output",type=Path)
    p.add_argument("--fail-if-not-perfect",action="store_true")
    args=p.parse_args()
    result=evaluate_reports([json.loads(path.read_text("utf-8")) for path in args.reports])
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if args.fail_if_not_perfect and result["status"]!="PASS":
        sys.exit(1)


if __name__=="__main__":
    main()
