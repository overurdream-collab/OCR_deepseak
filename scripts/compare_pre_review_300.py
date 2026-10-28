"""Strict comparison against PR #21 synthetic 300-case verified baseline."""
import argparse
import json
from pathlib import Path

def load(paths):
    rows={}
    for path in paths:
        report=json.loads(Path(path).read_text("utf-8"))
        if report.get("status")!="completed_real_ocr":
            raise ValueError("OCR not completed")
        for case in report["results"]:
            name=case["case"]
            if name in rows or not case["real_paddle_detected"] or case["page_failures"]:
                raise ValueError("duplicate/non-real OCR case "+name)
            rows[name]=case
    if len(rows)!=300:
        raise ValueError("expected exactly 300 complete synthetic cases")
    return rows

def compare(previous,current):
    old,new=load(previous),load(current)
    if old.keys()!=new.keys():
        raise ValueError("test cases changed")
    gained,lost,extra=[],[],[]
    for case in sorted(old):
        a,b=old[case],new[case]
        ca={x["field"]:x for x in a["checks"]}
        cb={x["field"]:x for x in b["checks"]}
        if ca.keys()!=cb.keys():
            raise ValueError("field keys changed")
        if b["extra_item_rows"]>a["extra_item_rows"]:
            extra.append(case)
        for field in ca:
            before,after=ca[field],cb[field]
            if before["expected"]!=after["expected"]:
                raise ValueError("truth changed for "+field)
            if before["matched"] and not after["matched"]:
                lost.append([case,field])
            if not before["matched"] and after["matched"]:
                gained.append([case,field])
            if after["matched"] and not after["linked_evidence"]:
                raise ValueError("missing source evidence "+case+" "+field)
    base=sum(x["matched"] for x in old.values())
    result=sum(x["matched"] for x in new.values())
    target=sum(x["total"] for x in new.values())
    if base!=5324 or target!=5776:
        raise ValueError("not the latest PR21 baseline")
    return {"status":"PASS" if not lost and not extra and result>=base else "BLOCKED",
            "baseline":base,"candidate":result,"total":target,
            "gained":gained,"lost":lost,"extra_row_regressions":extra}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--previous",nargs=6,required=True)
    p.add_argument("--current",nargs=6,required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    r=compare(a.previous,a.current)
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    Path(a.output).write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:len(v) if isinstance(v,list) else v for k,v in r.items()},ensure_ascii=False))
    if r["status"]!="PASS":
        raise SystemExit(1)
