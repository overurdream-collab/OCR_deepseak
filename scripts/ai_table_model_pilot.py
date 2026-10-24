"""Run REAL pretrained MIT Table Transformer models on new synthetic medical PDFs.

This is a visual layout acceptance experiment ONLY. Does not change MDIA
extracted invoice values. Only image pixels leave the local PDF renderer,
NOT the machine: model inference is fully local, and only public weights
are downloaded from Hugging Face.
"""
import argparse
import hashlib
import json
from pathlib import Path

from scripts.benchmark_invoice300 import (LAYOUTS, new_case, arabic_invoice,
                                           english_invoice, scan_pdf)
from mdia.table_ai import TableVision


def synthetic_cases(output_dir, shard=0, shards=2):
    output_dir.mkdir(parents=True, exist_ok=True)
    all_cases = [new_case(layout, i) for layout in LAYOUTS for i in (14, 17)]
    return [c for idx, c in enumerate(all_cases) if idx % shards == shard]


def generate_pdf(path, c):
    raw = path.with_suffix(".raw.pdf")
    if c["layout"].startswith("ar_"):
        arabic_invoice(raw, c)
    else:
        english_invoice(raw, c)
    if c["representation"] == "text":
        raw.rename(path)
    else:
        scan_pdf(raw, path, c["representation"], c["variant"])
        raw.unlink()


def render_preview(pdf):
    import pypdfium2 as pdfium
    document = pdfium.PdfDocument(str(pdf))
    return document[0].render(scale=144 / 72).to_pil().convert("RGB")


def overlay(image, prediction, dest):
    from PIL import ImageDraw
    image = image.copy()
    draw = ImageDraw.Draw(image)
    colors = {"table": (18, 132, 61), "table row": (224, 111, 24),
              "table column": (42, 85, 198)}
    w, h = image.size
    for p in prediction["proposals"]:
        for entry in [p["table"], *p["rows"], *p["columns"]]:
            box = entry["bbox"]
            draw.rectangle((box[0]*w, box[1]*h, box[2]*w, box[3]*h),
                           outline=colors.get(entry["label"], (120, 60, 180)), width=3)
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest)


def run(output_dir, shard=0, shards=2):
    root = Path(output_dir)
    pdf_dir = root / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    cases = synthetic_cases(pdf_dir, shard, shards)
    report = {"status": "incomplete", "scope": "synthetic_table_layout_only",
              "shard": shard, "shards": shards,
              "model_ids": ["microsoft/table-transformer-detection",
                            "microsoft/table-transformer-structure-recognition"],
              "records": [], "no_auto_financial_change": True}
    try:
        detector = TableVision(device="cpu")
        for c in cases:
            source = pdf_dir / (c["id"] + ".pdf")
            generate_pdf(source, c)
            original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            image = render_preview(source)
            prediction = detector.analyze(image)
            overlay(image, prediction, root / "overlays" / (c["id"] + ".png"))
            record = {"id": c["id"], "layout": c["layout"],
                      "representation": c["representation"], "pdf_sha256": original_hash,
                      "expected_items": len(c["rows"]), "predicted_tables": prediction["table_count"],
                      "predicted_rows": prediction["row_count"], "predicted_columns": prediction["column_count"],
                      "model_output": prediction,
                      "manual_review_required": True}
            report["records"].append(record)
            print(f"{record['id']} ({record['representation']}): "
                  f"tables={record['predicted_tables']}, rows={record['predicted_rows']}, "
                  f"columns={record['predicted_columns']}; actual item count={record['expected_items']}",
                  flush=True)
        report["status"] = "completed_visual_table_model_pilot"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        report["summary"] = {
            "processed": len(report["records"]),
            "found_at_least_one_table": sum(r["predicted_tables"] > 0 for r in report["records"]),
            "found_rows": sum(r["predicted_rows"] for r in report["records"]),
            "expected_items_not_accuracy_metric": sum(r["expected_items"] for r in report["records"]),
            "financial_fields_modified": 0}
        (root / "table_pilot_results.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print("FINAL STATUS", report["status"], "SUMMARY", report["summary"], flush=True)
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", default="results/table_transformer_pilot")
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--shards", type=int, default=2)
    args = p.parse_args()
    if args.shards <= 0 or not 0 <= args.shard < args.shards:
        raise SystemExit("invalid shard")
    run(args.output_dir, args.shard, args.shards)
