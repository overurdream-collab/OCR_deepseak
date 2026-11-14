"""Reproduce source-level mismatch cases with actual local PaddleOCR.

This is synthetic-only diagnostics. Preserve original OCR source and the
extracted rows so we can distinguish recognition errors from bad row matching.
"""
import argparse
import json
import os
import tempfile
from pathlib import Path

from scripts.benchmark_invoice300 import all_cases, english_invoice, arabic_invoice, scan_pdf
from mdia.pipeline import process_job
from mdia.store import Store


DEFAULT_CASES = (
    "ar_shaped_10", "ar_shaped_16", "ar_visual_16", "ar_visual_32",
    "ar_mixed_42", "ar_shaped_53", "en_compact_12", "en_reordered_14",
)


def run(ids, out):
    cases = {case["id"]: case for case in all_cases()}
    if any(i not in cases for i in ids):
        raise ValueError("unknown case")
    output = {"synthetic_only": True, "records": []}
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        for case_id in ids:
            c = cases[case_id]
            original = base / (case_id + "_original.pdf")
            pdf = base / (case_id + ".pdf")
            (arabic_invoice if c["layout"].startswith("ar_") else english_invoice)(original, c)
            if c["representation"] == "text":
                original.rename(pdf)
            else:
                scan_pdf(original, pdf, c["representation"], c["variant"])
            store = Store(base / case_id)
            jid = store.create(pdf.name, pdf.read_bytes())
            prev = os.environ.get("MDIA_OCR_ENGINE")
            try:
                os.environ["MDIA_OCR_ENGINE"] = "paddle_arabic"
                result = process_job(store, jid, ocr_mode="force")
            finally:
                if prev is None:
                    os.environ.pop("MDIA_OCR_ENGINE", None)
                else:
                    os.environ["MDIA_OCR_ENGINE"] = prev
            if result is None or not result.get("documents"):
                raise RuntimeError("failed to process " + case_id)
            saved = [json.loads(p.read_text("utf-8")) for p in
                     sorted(store.path(jid, "pages").glob("*.json"))]
            if not any(p["flags"].get("ocr_engine") == "paddleocr-v5-arabic" for p in saved):
                raise RuntimeError("Paddle did not run")
            docs = result["documents"]
            fields = ("service_name", "quantity", "unit_price", "line_total")
            records = [{
                "type": doc["document_type"],
                "items": [
                    {"id": it["id"], **{key: {k: it[key].get(k) for k in
                        ("raw", "value", "status", "verification", "review_reasons", "page")}
                        for key in fields}}
                    for it in doc["invoice_items"]
                ],
                "patient_raw": (doc.get("patient", {}).get("name") or {}).get("raw"),
                "invoice_number_raw": ((doc.get("invoices") or [{}])[0].get("invoice_number") or {}).get("raw"),
                "queue_reasons": [q.get("reasons") for q in doc["requires_human_review"]],
            } for doc in docs]
            output["records"].append({
                "id": case_id, "layout": c["layout"], "representation": c["representation"],
                "synthetic_source": c["rows"],
                "pages": [
                    {"page": p["number"], "words": [
                        {"text": w["text"],"x0": w["x0"],"y0": w["y0"],
                         "x1": w["x1"],"y1": w["y1"],"conf": w["conf"]}
                        for w in p["words"]
                    ]} for p in saved],
                "documents": records,
            })
            print(case_id, "observed rows", sum(len(d["items"]) for d in records), flush=True)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n", encoding="utf-8")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--cases",nargs="+",default=list(DEFAULT_CASES))
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    run(args.cases,args.out)
