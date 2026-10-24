"""Actual PP-DocLayout-S table-region benchmark on SAME 12 synthetic PDFs as Table Transformer."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import ImageDraw
from mdia.paddle_layout import PaddleLayoutPilot
from scripts.ai_table_model_pilot import synthetic_cases, generate_pdf, render_preview


def run(output_dir, shard=0, shards=2, model_name="PicoDet_layout_1x_table"):
    root=Path(output_dir)
    (root/"pdfs").mkdir(parents=True, exist_ok=True)
    cases=synthetic_cases(root/"pdfs",shard,shards)
    report={"status":"incomplete","scope":"synthetic_table_region_only",
            "engine":model_name, "records":[], "no_financial_writes":True}
    try:
        model=PaddleLayoutPilot(model_name=model_name)
        for c in cases:
            pdf=root/"pdfs"/(c["id"]+".pdf")
            generate_pdf(pdf,c)
            image=render_preview(pdf)
            image_path=root/"pdfs"/(c["id"]+".png")
            image.save(image_path)
            proposal=model.analyze(image_path,image.size)
            annotated=image.copy()
            draw=ImageDraw.Draw(annotated)
            for p in proposal["table_regions"]:
                b=p["bbox"]
                draw.rectangle((b[0]*image.width,b[1]*image.height,b[2]*image.width,b[3]*image.height),
                               outline=(21,134,66),width=4)
            (root/"overlays").mkdir(parents=True,exist_ok=True)
            annotated.save(root/"overlays"/(c["id"]+".png"))
            record={"id":c["id"],"layout":c["layout"],"representation":c["representation"],
                    "expected_items":len(c["rows"]),"pdf_sha256":hashlib.sha256(pdf.read_bytes()).hexdigest(),
                    "detected_tables":proposal["table_count"],"proposal":proposal}
            report["records"].append(record)
            print(c["id"],c["layout"],"tables",proposal["table_count"],
                  "expected item count",len(c["rows"]),flush=True)
        report["status"]="completed_real_layout_pilot"
    except Exception as e:
        report["status"]="failed"
        report["error"]=f"{type(e).__name__}: {e}"
        raise
    finally:
        report["summary"]={"processed":len(report["records"]),
                           "tables_present":sum(x["detected_tables"]>0 for x in report["records"]),
                           "arabic_detected":sum(x["detected_tables"]>0 and x["layout"].startswith("ar_")
                                                 for x in report["records"]),
                           "english_detected":sum(x["detected_tables"]>0 and x["layout"].startswith("en_")
                                                 for x in report["records"]),
                           "changed_financial_fields":0}
        (root/"layout_results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),"utf-8")
        print("STATUS",report["status"],"SUMMARY",report["summary"],flush=True)
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--shards",type=int,default=2)
    p.add_argument("--output-dir",default="results/ai_paddle_layout")
    p.add_argument("--model",choices=["PP-DocLayout-S","PicoDet_layout_1x_table"],default="PicoDet_layout_1x_table")
    args=p.parse_args()
    if args.shards<1 or not 0<=args.shard<args.shards: raise SystemExit("invalid shard")
    run(args.output_dir,args.shard,args.shards,args.model)
