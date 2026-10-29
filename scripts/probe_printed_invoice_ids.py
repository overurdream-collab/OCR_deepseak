"""Live original-PDF probe: exactly four English invoice ID OCR suffix errors.

No expected value is passed to MDIA. Ground truth is used ONLY for scoring.
The original PDF is generated once and source PDF crop OCR is forced locally.
"""
import json
import os
import tempfile
from pathlib import Path

from mdia.pipeline import process_job
from mdia.store import Store
from scripts.benchmark_invoice300 import new_case, english_invoice, scan_pdf, score_record

TARGETS=(
    ("en_standard",33),
    ("en_reordered",48),
    ("en_reordered",59),
    ("en_compact",54),
)


def main():
    results=[]
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory)
        for layout,index in TARGETS:
            case=new_case(layout,index)
            src=tmp/(case["id"]+"_src.pdf")
            dst=tmp/(case["id"]+".pdf")
            english_invoice(src,case)
            if case["representation"]=="text":
                src.rename(dst)
            else:
                scan_pdf(src,dst,case["representation"],case["variant"])
            store=Store(tmp/case["id"])
            jid=store.create(dst.name,dst.read_bytes())
            os.environ["MDIA_OCR_ENGINE"]="paddle_arabic"
            result=process_job(store,jid,ocr_mode="force")
            if not result:
                raise RuntimeError("OCR failed: "+case["id"])
            pages=[json.loads(path.read_text("utf-8")) for path in store.path(jid,"pages").glob("*.json")]
            flags=[p.get("flags",{}) for p in pages]
            report=score_record(case,result,"paddle_arabic",flags)
            number=next(x for x in report["checks"] if x["field"]=="invoice.number")
            output={"case":case["id"],"expected":number["expected"],
                    "actual":number["actual"],"matched":number["matched"],
                    "linked_evidence":number["linked_evidence"],
                    "real_paddle_detected":report["real_paddle_detected"],
                    "other_matched":report["matched"],"other_total":report["total"]}
            results.append(output)
            print(json.dumps(output,ensure_ascii=False),flush=True)
    Path("results").mkdir(exist_ok=True)
    Path("results/printed_invoice_id_probe.json").write_text(
        json.dumps(results,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if len(results)!=4 or not all(x["matched"] and x["linked_evidence"] and x["real_paddle_detected"]
                                  for x in results):
        raise SystemExit("BLOCKED: one or more source invoice numbers not independently corrected")
    print("PASS: 4/4 source-printed IDs recovered, no guessed expected value")


if __name__=="__main__":
    main()
