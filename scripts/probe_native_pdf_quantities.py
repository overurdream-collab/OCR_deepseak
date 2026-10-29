"""Real PaddleOCR test of native original-PDF quantity-word recovery.

Synthetic generator supplies expected values exclusively to the scorer, never
to MDIA's extraction or recovery logic.
"""
import json
import os
import tempfile
from pathlib import Path

from scripts.benchmark_invoice300 import new_case,english_invoice,arabic_invoice,scan_pdf,score_record
from mdia.pipeline import process_job
from mdia.store import Store


TARGETS=(
    ("ar_shaped",12), ("ar_visual",36), ("en_compact",12),
    ("ar_mixed",36), ("ar_mixed",24), ("ar_visual",42)
)


def main():
    out=[]
    with tempfile.TemporaryDirectory() as d:
        root=Path(d)
        for layout,index in TARGETS:
            c=new_case(layout,index)
            src=root/(c["id"]+"_src.pdf")
            dst=root/(c["id"]+".pdf")
            (arabic_invoice if layout.startswith("ar_") else english_invoice)(src,c)
            if c["representation"]=="text":
                src.rename(dst)
            else:
                scan_pdf(src,dst,c["representation"],c["variant"])
            store=Store(root/c["id"])
            jid=store.create(dst.name,dst.read_bytes())
            os.environ["MDIA_OCR_ENGINE"]="paddle_arabic"
            result=process_job(store,jid,ocr_mode="force")
            if not result:
                raise RuntimeError("source OCR failure "+c["id"])
            flags=[json.loads(x.read_text("utf-8")).get("flags",{})
                   for x in store.path(jid,"pages").glob("*.json")]
            rec=score_record(c,result,"paddle_arabic",flags)
            qs=[x for x in rec["checks"] if x["field"].endswith(".qty")]
            src_result={"case":c["id"],"representation":c["representation"],
                        "real_paddle_detected":rec["real_paddle_detected"],
                        "matched_qty":sum(x["matched"] for x in qs),
                        "expected_qty":len(qs),
                        "quantities":[{"field":x["field"],"expected":x["expected"],
                                      "actual":x["actual"],"matched":x["matched"],
                                      "linked_evidence":x["linked_evidence"]} for x in qs]}
            out.append(src_result)
            print(json.dumps(src_result,ensure_ascii=False),flush=True)
    Path("results").mkdir(exist_ok=True)
    Path("results/native_pdf_quantity_probe.json").write_text(
        json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if len(out)!=len(TARGETS) or not all(x["real_paddle_detected"] for x in out):
        raise SystemExit("missing real OCR")
    print("SOURCE TEST COMPLETED — evaluate actual numbers against baseline")


if __name__=="__main__":
    main()
