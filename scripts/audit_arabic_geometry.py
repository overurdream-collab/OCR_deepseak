"""Synthetic Arabic OCR evidence audit: highlighted PDF positions, never word accuracy."""
import argparse
import json
import os
import re
import tempfile
from pathlib import Path

from PIL import ImageDraw

from mdia.pipeline import process_job
from mdia.store import Store
from scripts.compare_arabic_ocr import prepare
from scripts.compare_structured_arabic import GT, row_by_name, norm, same, val
from tests.arabic_samples import invoice as arabic_invoice, prescription as arabic_prescription
from tests.make_samples import H

# Independent source layout rows in points from page TOP, from the synthetic generator.
BASELINES = {"invoice_no": 96, "patient_invoice": 128, "invoice_total": 238,
             "item1": 200, "item2": 215, "patient_rx": 96,
             "medicine1": 134, "medicine2": 150}
TOLERANCE_PT = 8
EXPANDED = {"invoice_eastern.pdf": "invoice_shaped.pdf",
            "invoice_diacritics.pdf": "invoice_shaped.pdf",
            "prescription_logical.pdf": "prescription_shaped.pdf"}


def fixtures(out: Path):
    prepare(out)
    arabic_invoice(out / "invoice_eastern.pdf", "shaped", eastern=True)
    arabic_invoice(out / "invoice_diacritics.pdf", "shaped", diacritics=True)
    arabic_prescription(out / "prescription_logical.pdf", "logical")
    return [*GT, *EXPANDED]


def targets(doc, truth):
    out = [("patient.name", truth["patient"], doc.get("patient", {}).get("name", {}),
            "patient_invoice" if "items" in truth else "patient_rx")]
    if "items" in truth:
        inv = (doc.get("invoices") or [{}])[0]
        out += [("invoice.number", truth["number"], inv.get("invoice_number", {}), "invoice_no"),
                ("invoice.total", truth["total"], inv.get("invoice_total", {}), "invoice_total")]
        for i, item in enumerate(truth["items"], 1):
            name, qty, unit_price, line_total = item
            row = row_by_name(doc.get("invoice_items", []), "service_name", name)
            for key, expected, attr in (("name", name, "service_name"), ("qty", qty, "quantity"),
                                        ("unit_price", unit_price, "unit_price"),
                                        ("line_total", line_total, "line_total")):
                out.append((f"items.{i}.{key}", expected, row.get(attr, {}), f"item{i}"))
    else:
        for i, med in enumerate(truth.get("medicines", []), 1):
            name, strength = med
            row = row_by_name(doc.get("medications", []), "brand_name", name)
            out += [(f"medicines.{i}.name", name, row.get("brand_name", {}), f"medicine{i}"),
                    (f"medicines.{i}.strength", strength, row.get("strength", {}), f"medicine{i}")]
    return out


def check_geometry(field, evidence, band, expected, label, expected_page=1):
    """Check matching value, internal evidence chain and expected PDF ROW (Y only).

    This is NOT an independent word-box accuracy test. All included synthetic
    source documents are one page, so both record and evidence MUST cite page 1.
    """
    raw = val(field)
    match = (same(expected, raw) if not label.endswith(".strength") else
             bool(raw and re.search(r"(?<!\d)500(?!\d)", norm(raw))))
    bbox = evidence.get("bbox") if isinstance(evidence, dict) else None
    geom = (isinstance(field, dict) and isinstance(bbox, list) and len(bbox) == 4
            and all(isinstance(v, (float, int)) and 0 <= v <= 1 for v in bbox)
            and bbox[0] < bbox[2] and bbox[1] < bbox[3]
            and field.get("page") == evidence.get("page") == expected_page)
    # Integrity of the program's evidence reference, not proof that its line
    # text or interpolated x-coordinates match independently observed pixels.
    chain = bool(isinstance(field, dict) and isinstance(evidence, dict)
                 and field.get("evidence_id") and field["evidence_id"] == evidence.get("id")
                 and isinstance(field.get("raw"), str)
                 and field["raw"] == evidence.get("matched_text")
                 and str(evidence.get("text") or "").strip())
    offset = round((bbox[1] + bbox[3]) * H / 2 - BASELINES[band], 2) if geom else None
    return {"field": label, "expected": expected, "actual": raw, "value_match": match,
            "evidence_id": field.get("evidence_id") if isinstance(field, dict) else None,
            "page": field.get("page") if isinstance(field, dict) else None,
            "bbox": bbox if geom else None, "geometry_valid": bool(geom),
            "evidence_chain_valid": chain,
            "row_y_offset_pt": offset, "expected_row_baseline_from_top_pt": BASELINES[band],
            "row_band_consistent": bool(match and geom and chain and abs(offset) <= TOLERANCE_PT)}


def annotate(pdf_path, records, dst, engine):
    import pypdfium2 as pdfium
    im = pdfium.PdfDocument(str(pdf_path))[0].render(scale=2).to_pil().convert("RGB")
    draw = ImageDraw.Draw(im)
    w, h = im.size
    for pt in sorted({r["expected_row_baseline_from_top_pt"] for r in records}):
        y = round(pt * h / H)
        draw.line((0, y, w, y), fill=(48, 91, 204), width=2)
    for i, rec in enumerate(records, 1):
        if not rec["bbox"]:
            continue
        b = rec["bbox"]
        coords = (b[0]*w, b[1]*h, b[2]*w, b[3]*h)
        color = (30, 145, 61) if rec["row_band_consistent"] else (200, 42, 42)
        draw.rectangle(coords, outline=color, width=3)
        draw.text((max(2, coords[0]), max(2, coords[1]-13)), str(i), fill=color)
    draw.rectangle((2, 2, w-2, 48), fill="white")
    draw.text((10, 8), f"{engine}: BLUE=source row / GREEN=match+row / RED=mismatch", fill="black")
    draw.text((10, 27), "Paddle word boxes INTERPOLATED: this is NOT word-geometry accuracy.", fill="black")
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, optimize=True)


def run(output, image_dir, engines=("tesseract", "paddle_arabic")):
    output, image_dir = Path(output), Path(image_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)
    result = {"status": "incomplete", "scope": "synthetic_source_row_geometry_only",
              "word_box_accuracy_measured": False, "paddle_token_boxes_interpolated": True,
              "source_row_tolerance_pt": TOLERANCE_PT,
              "engines": list(engines), "records": [], "summary": {}}
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        names = fixtures(root / "pdf")
        try:
            for engine in engines:
                samples = []
                for filename in names:
                    truth = GT[EXPANDED.get(filename, filename)]
                    pdf = root / "pdf" / filename
                    store = Store(root / "jobs" / engine / filename)
                    job = store.create(filename, pdf.read_bytes())
                    previous = os.environ.get("MDIA_OCR_ENGINE")
                    try:
                        os.environ["MDIA_OCR_ENGINE"] = engine
                        output_doc = process_job(store, job, ocr_mode="force")
                    finally:
                        if previous is None:
                            os.environ.pop("MDIA_OCR_ENGINE", None)
                        else:
                            os.environ["MDIA_OCR_ENGINE"] = previous
                    if output_doc is None or any(
                        any(w.get("kind") == "page_failed" for w in p["warnings"])
                        for p in output_doc.get("page_info", [])
                    ):
                        raise RuntimeError(f"{engine}/{filename}: OCR processing failed")
                    docs = output_doc["documents"]
                    doc = next((d for d in docs if d.get("document_type") == truth["type"]),
                               docs[0] if docs else {})
                    if engine == "paddle_arabic" and not any(
                        w.get("kind") == "paddle_line_geometry_only"
                        for w in doc.get("warnings", [])
                    ):
                        raise RuntimeError(f"{engine}/{filename}: missing approximation warning")
                    evs = {ev["id"]: ev for ev in doc.get("evidence", [])}
                    fields = []
                    for label, expected, field, band in targets(doc, truth):
                        ev = evs.get(field.get("evidence_id")) if isinstance(field, dict) else None
                        fields.append(check_geometry(field, ev, band, expected, label))
                    overlay = image_dir / f"{engine}_{filename.replace('.pdf', '')}.png"
                    annotate(pdf, fields, overlay, engine)
                    item = {"engine": engine, "source": filename,
                            "processing_status": output_doc["processing_status"],
                            "cross_engine_word_matches": sum(x.get("cross_engine_word_matches", 0) for x in output_doc.get("page_info", [])),
                            "word_alignment_opt_in": any(x.get("word_alignment_opt_in", False) for x in output_doc.get("page_info", [])),
                            "expected_fields": len(fields),
                            "matching_values": sum(c["value_match"] for c in fields),
                            "evidence_chain_valid_values": sum(c["value_match"] and c["evidence_chain_valid"] for c in fields),
                            "row_consistent_values": sum(c["row_band_consistent"] for c in fields),
                            "overlay": str(overlay), "fields": fields}
                    samples.append(item)
                    result["records"].append(item)
                    print(f"{engine}/{filename}: matches {item['matching_values']}/{len(fields)}, "
                          f"correct source row {item['row_consistent_values']}/{len(fields)}")
                result["summary"][engine] = {
                    "documents": len(samples),
                    "cross_engine_word_matches": sum(x["cross_engine_word_matches"] for x in samples),
                    "matching_values": sum(x["matching_values"] for x in samples),
                    "evidence_chain_valid_values": sum(x["evidence_chain_valid_values"] for x in samples),
                    "row_consistent_values": sum(x["row_consistent_values"] for x in samples),
                    "expected_fields": sum(x["expected_fields"] for x in samples),
                }
            result["status"] = "completed_synthetic_position_audit"
        except Exception as err:
            result["status"] = "failed"
            result["error"] = f"{type(err).__name__}: {err}"
            raise
        finally:
            output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--output", default="results/arabic_geometry_audit.json")
    cli.add_argument("--image-dir", default="results/geometry_overlays")
    cli.add_argument("--engines", nargs="+", choices=["tesseract", "paddle_arabic"],
                     default=["tesseract", "paddle_arabic"])
    args = cli.parse_args()
    run(args.output, args.image_dir, args.engines)
