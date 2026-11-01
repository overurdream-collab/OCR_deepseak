"""Compare candidate and previously VERIFIED PR #20 real-OCR benchmark case-by-case.

Fails on ANY previously correct field lost, ANY extra row inflation,
changed synthetic case IDs, non-completion, or missing evidence.
"""
import argparse
import json
from pathlib import Path


def compare(previous, current):
    def collect(paths):
        cases={}
        for path in paths:
            d=json.loads(Path(path).read_text(encoding="utf-8"))
            if d.get("status")!="completed_real_ocr":
                raise ValueError("partial synthetic 300 OCR report")
            for r in d.get("results",[]):
                if not r.get("real_paddle_detected") or r.get("page_failures"):
                    raise ValueError("non-Paddle OCR or page failure")
                if r["case"] in cases:
                    raise ValueError("duplicate case "+r["case"])
                cases[r["case"]]=r
        if len(cases)!=300: raise ValueError("expected 300 distinct synthetic cases")
        return cases

    old,new=collect(previous),collect(current)
    if old.keys()!=new.keys():
        raise ValueError("changed synthetic invoice identifiers")
    gained,lost,extra,detail=[],[],[],[]
    for name,base in sorted(old.items()):
        candidate=new[name]
        oldcheck={x["field"]:x for x in base["checks"]}
        newcheck={x["field"]:x for x in candidate["checks"]}
        if oldcheck.keys()!=newcheck.keys():
            raise ValueError(name+": changed field masks")
        for key,field in oldcheck.items():
            newer=newcheck[key]
            if field["expected"]!=newer["expected"]:
                raise ValueError(name+": synthetic truth changed")
            if field["matched"] and not newer["matched"]:
                lost.append((name,key))
            elif newer["matched"] and not field["matched"]:
                gained.append((name,key))
            if newer["matched"] and not newer["linked_evidence"]:
                raise ValueError(name+":"+key+": matched field lacks linked evidence")
        if candidate["extra_item_rows"]>base["extra_item_rows"]:
            extra.append(name)
        if candidate.get("runtime_error"):
            raise ValueError(name+": runtime failure")
        if candidate["matched"]!=base["matched"]:
            detail.append({"case":name,"old":base["matched"],"new":candidate["matched"]})
    report={
        "baseline_correct":sum(r["matched"] for r in old.values()),
        "candidate_correct":sum(r["matched"] for r in new.values()),
        "expected":sum(r["total"] for r in new.values()),
        "gained_fields":gained,"lost_fields":lost,
        "new_extra_rows_in_cases":extra,
        "changed_cases":detail,
        "status":"PASS" if not lost and not extra else "BLOCKED",
    }
    if report["baseline_correct"]!=5285 or report["expected"]!=5776:
        raise ValueError("wrong PR #20 baseline or mutated benchmark")
    return report


def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--previous",nargs=6,required=True)
    ap.add_argument("--current",nargs=6,required=True)
    ap.add_argument("--output",type=Path)
    args=ap.parse_args(argv)
    r=compare(args.previous,args.current)
    payload=json.dumps(r,ensure_ascii=False,indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(payload+"\n",encoding="utf-8")
    print(payload)
    if r["status"]!="PASS":
        raise SystemExit(1)


if __name__=="__main__":
    main()
