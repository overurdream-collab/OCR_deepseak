"""Large reproducible, fully SYNTHETIC medical-invoice stress benchmark.

60 randomized yet deterministic PDFs; 6 layouts x 10 variants.
Never uses real people, medical records, external data or paid APIs.
Reports ALL OCR errors as observed failures rather than hiding them.
"""
import argparse
import hashlib
import json
import os
import random
import re
import shutil
import tempfile
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from mdia.pipeline import process_job
from mdia.store import Store
from scripts.compare_structured_arabic import norm, same, val, row_by_name, valid_evidence
from tests.make_samples import Doc, W, H
from tests.arabic_samples import put

VERSION = "SYNTHETIC-INVOICE-60-v1"
SEED = 20261025
LAYOUTS = ("en_standard", "en_reordered", "en_compact",
           "ar_shaped", "ar_visual", "ar_mixed")
PATIENT_EN = ("Test Person One", "Sample Patient Seven", "Mariam Nasser Sample",
              "Fictional Ahmad Ali", "Synthetic Noor Khalid")
PATIENT_AR = ("خالد يوسف", "ليلى حسن", "سارة عمر", "فاطمة أحمد", "علي ناصر")
NAMES_EN = (
    "General Consultation", "Complete Blood Count", "Lipid Profile",
    "Chest X-Ray", "Ultrasound Abdomen", "Glucose Test", "Creatinine Test",
    "Dental Cleaning", "Physiotherapy Session", "Room Charges",
    "Paracetamol Tablets", "Amoxicillin Capsules")
NAMES_AR = (
    "كشف استشاري", "تحليل دم شامل", "تحليل سكر صائم",
    "أشعة سينية", "موجات فوق صوتية", "تخطيط قلب", "تحليل وظائف الكلى",
    "جلسة علاج طبيعي", "أجرة غرفة", "رسوم تمريض",
    "أقراص باراسيتامول", "كبسولات أموكسيسيلين")
EASTERN = str.maketrans("0123456789.,", "٠١٢٣٤٥٦٧٨٩٫٬")


def number(s, eastern=False):
    return str(s).translate(EASTERN) if eastern else str(s)


def money(n, grouped=False):
    return f"{n:,.2f}" if grouped else f"{n:.2f}"


def new_case(layout, index):
    rnd = random.Random(SEED + LAYOUTS.index(layout) * 100 + index)
    ar = layout.startswith("ar_")
    names = NAMES_AR if ar else NAMES_EN
    chosen = rnd.sample(names, rnd.randint(2, 5))
    rows = []
    for name in chosen:
        qty = rnd.randint(1, 4)
        cents = rnd.choice((0, 25, 50, 75))
        unit_price = Decimal(rnd.randint(9, 420)) + Decimal(cents) / 100
        line_total = unit_price * qty
        rows.append({"name": name, "qty": qty, "price": float(unit_price),
                     "total": float(line_total)})
    subtotal = sum(Decimal(str(r["total"])) for r in rows)
    discount = (Decimal("15.00") if index in (4, 8) else Decimal("0"))
    tax = (subtotal - discount) * (Decimal(".05") if index in (3, 7) else Decimal("0"))
    tax = tax.quantize(Decimal(".01"))
    total = (subtotal - discount + tax).quantize(Decimal(".01"))
    # One printed arithmetic discrepancy, for warning-only checks.
    printed_discrepancy = index == 9
    if printed_discrepancy:
        total += Decimal("2.00")
    mode = ("text" if index % 5 in (0, 3) else
            "scan" if index % 5 == 1 else
            "blur" if index % 5 == 2 else "skew")
    case = {
        "id": f"{layout}_{index:02d}", "layout": layout, "variant": index,
        "patient": (PATIENT_AR if ar else PATIENT_EN)[index % 5],
        "invoice_number": f"INV-{710000 + LAYOUTS.index(layout) * 100 + index}",
        "subtotal": float(subtotal), "discount": float(discount),
        "tax": float(tax), "invoice_total": float(total),
        "printed_discrepancy": printed_discrepancy,
        "rows": rows, "representation": mode, "pages": 2 if index == 9 else 1,
        "currency": "SAR" if index % 2 == 0 else "YER",
    }
    return case


def all_cases():
    return [new_case(layout, i) for layout in LAYOUTS for i in range(10)]


def header_en(d, c, continuation=False):
    if continuation:
        d.line(f"Sample Medical Center — Invoice {c['invoice_number']} (continued)", gap=23)
        return
    d.line("Sample Medical Center", size=15, bold=True, gap=24)
    d.line("Medical Invoice", size=12, bold=True, gap=22)
    d.line(f"Invoice No: {c['invoice_number']}    Date: 2026-08-15", gap=16)
    d.line(f"Patient Name: {c['patient']}", gap=16)
    d.line(f"Currency: {c['currency']}", gap=20)


def english_invoice(path, c):
    d = Doc(path)
    header_en(d, c)
    layout = c["layout"]
    if layout == "en_standard":
        xx = (46, 328, 387, 482)
        hd = ("Description", "Qty", "Unit Price", "Total")
    elif layout == "en_reordered":
        xx = (44, 320, 400, 479)
        hd = ("Description", "Amount", "Qty", "Price")
    else:
        xx = (44, 318, 387, 480)
        hd = ("Description", "Qty", "Unit", "Line")
    rows = c["rows"]
    groups = [rows] if c["pages"] == 1 else [rows[:2], rows[2:]]
    for page, group in enumerate(groups):
        if page:
            d.page_break()
            header_en(d, c, continuation=True)
        for x, title in zip(xx, hd):
            d.t(x, d.y, title, bold=True)
        d.y -= 12
        if layout == "en_compact":
            d.t(xx[2], d.y, "Price", bold=True)
            d.t(xx[3], d.y, "Total", bold=True)
            d.y -= 14
        else:
            d.y -= 4
        for item in group:
            q, p, t = str(item["qty"]), money(item["price"]), money(item["total"])
            cells = (item["name"], t, q, p) if layout == "en_reordered" else (
                item["name"], q, p, t)
            for x, field in zip(xx, cells):
                d.t(x, d.y, field, size=9)
            d.y -= 18
    d.y -= 10
    for label, key in (("Subtotal", "subtotal"), ("Discount", "discount"),
                       ("VAT", "tax"), ("Total", "invoice_total")):
        if key in ("discount", "tax") and not c[key]:
            continue
        d.t(376, d.y, label, bold=(key == "invoice_total"))
        d.t(470, d.y, money(c[key]), bold=(key == "invoice_total"))
        d.y -= 17
    if c["printed_discrepancy"]:
        d.t(45, d.y-6, "SYNTHETIC: total deliberately differs by 2.00", size=8)
    d.save()


def header_ar(d, c, mode, mixed, continued=False):
    R = W - 36
    put(d, R, d.y, "مركز الاختبار الطبي" if not mixed else "مستشفى التجربة",
        mode, size=14, bold=True)
    d.y -= 24
    if mixed:
        d.t(40, d.y, "Hospital Invoice", size=12, bold=True)
    else:
        put(d, R, d.y, "فاتورة طبية", mode, size=12, bold=True)
    d.y -= 20
    put(d, R, d.y, "رقم الفاتورة:", mode)
    put(d, R - 112, d.y, c["invoice_number"], mode)
    d.y -= 17
    if not continued:
        put(d, R, d.y, "اسم المريض:", mode)
        put(d, R - 94, d.y, c["patient"], mode)
        d.y -= 17
    put(d, R, d.y, "العملة:", mode)
    put(d, R - 57, d.y, c["currency"], mode)
    d.y -= 24


def arabic_invoice(path, c):
    mode = "shaped" if c["layout"] in ("ar_shaped", "ar_mixed") else "visual"
    mixed = c["layout"] == "ar_mixed"
    d = Doc(path)
    R = W - 36
    groups = [c["rows"]] if c["pages"] == 1 else [c["rows"][:2], c["rows"][2:]]
    east = c["variant"] in (2, 3, 6, 7)
    for page, group in enumerate(groups):
        if page:
            d.page_break()
        header_ar(d, c, mode, mixed, continued=page > 0)
        # Arabic description at the right, numbers on the left.
        cols = [("البيان", R), ("الكمية", R-270),
                ("السعر", R-345), ("الإجمالي", R-449)]
        if c["variant"] != 8:  # intentionally unheaded, challenge case
            for label, x in cols:
                put(d, x, d.y, label, mode, size=9, bold=True)
            d.y -= 20
        for row in group:
            put(d, R, d.y, row["name"], mode, size=9)
            put(d, R-270, d.y, number(row["qty"], east), mode, size=9)
            put(d, R-345, d.y, number(money(row["price"]), east), mode, size=9)
            put(d, R-449, d.y, number(money(row["total"]), east), mode, size=9)
            d.y -= 18
    d.y -= 12
    for label, key in (("المجموع قبل الخصم", "subtotal"),
                       ("الخصم", "discount"), ("الضريبة", "tax"),
                       ("إجمالي الفاتورة", "invoice_total")):
        if key in ("discount", "tax") and not c[key]:
            continue
        put(d, R-260, d.y, label, mode, size=9, bold=(key=="invoice_total"))
        put(d, R-449, d.y, number(money(c[key]), east), mode, size=9,
            bold=(key=="invoice_total"))
        d.y -= 18
    d.save()


def scan_pdf(src, dst, kind):
    import pypdfium2 as pdfium
    from PIL import Image, ImageFilter
    pdf = pdfium.PdfDocument(str(src))
    imgs = []
    for page in pdf:
        im = page.render(scale=180/72).to_pil().convert("RGB")
        if kind == "blur":
            im = im.filter(ImageFilter.GaussianBlur(0.7))
        if kind == "skew":
            im = im.rotate(1.35, resample=Image.Resampling.BICUBIC,
                           fillcolor="white", expand=False)
        imgs.append(im)
    imgs[0].save(str(dst), save_all=True, append_images=imgs[1:],
                 resolution=180)


def generate_cases(output_dir, shard=0, shards=3):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = [c for i, c in enumerate(all_cases()) if i % shards == shard]
    for c in cases:
        dest = output_dir / f"{c['id']}.pdf"
        src = output_dir / f"_{c['id']}_source.pdf"
        if c["layout"].startswith("ar_"):
            arabic_invoice(src, c)
        else:
            english_invoice(src, c)
        if c["representation"] == "text":
            src.rename(dest)
        else:
            scan_pdf(src, dest, c["representation"])
            src.unlink()
        c["file_sha256"] = hashlib.sha256(dest.read_bytes()).hexdigest()
        c["size_bytes"] = dest.stat().st_size
    (output_dir / "ground_truth.json").write_text(
        json.dumps({"seed": SEED, "version": VERSION, "shard": shard,
                    "shards": shards, "cases": cases},
                   ensure_ascii=False, indent=2), "utf-8")
    return cases


def score_record(c, result, engine, flags):
    docs = (result or {}).get("documents", [])
    doc = max(docs, key=lambda d: len(d.get("invoice_items", [])),
              default={})
    rows = doc.get("invoice_items", [])
    invoice = (doc.get("invoices") or [{}])[0]
    checks = []
    def test(field, expected, obj, allow_numbered=False):
        actual = val(obj)
        if allow_numbered and isinstance(actual, str):
            actual = re.sub(r"^\d+[.\-:]?\s*", "", norm(actual))
        matched = same(expected, actual)
        checks.append({"field": field, "expected": expected, "actual": val(obj),
                       "matched": bool(matched),
                       "linked_evidence": bool(matched and valid_evidence(obj, doc))})
    test("patient.name", c["patient"], doc.get("patient", {}).get("name"))
    test("invoice.number", c["invoice_number"], invoice.get("invoice_number"))
    test("invoice.total", c["invoice_total"], invoice.get("invoice_total"))
    for i, row in enumerate(c["rows"], 1):
        found = row_by_name(rows, "service_name", row["name"])
        for key, attr in (("name", "service_name"), ("qty", "quantity"),
                          ("price", "unit_price"), ("total", "line_total")):
            test(f"item.{i}.{key}", row[key], found.get(attr), allow_numbered=key=="name")
    faults = [p for p in (result or {}).get("page_info", [])
              if any(w.get("kind") == "page_failed" for w in p.get("warnings", []))]
    matched_names = sum(ch["matched"] for ch in checks if re.fullmatch(r"item\.\d+\.name", ch["field"]))
    return {
        "case": c["id"], "layout": c["layout"], "representation": c["representation"],
        "pages": c["pages"], "model": engine, "status": (result or {}).get("processing_status", "failed"),
        "actual_type": doc.get("document_type"),
        "matched": sum(x["matched"] for x in checks),
        "with_evidence": sum(x["linked_evidence"] for x in checks),
        "total": len(checks), "matched_item_names": matched_names,
        "expected_item_rows": len(c["rows"]), "extracted_item_rows": len(rows),
        "extra_item_rows": max(0, len(rows)-matched_names),
        "page_failures": faults,
        "real_paddle_detected": any(f.get("ocr_engine") == "paddleocr-v5-arabic" for f in flags),
        "review_required": bool(doc.get("requires_human_review")),
        "checks": checks,
    }


def run(output_dir, shard=0, shards=3, engines=("tesseract", "paddle_arabic")):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = output_dir / "pdfs"
    cases = generate_cases(pdf_dir, shard=shard, shards=shards)
    report = {"status": "incomplete", "seed": SEED, "version": VERSION,
              "cases": len(cases), "shard": shard, "shards": shards,
              "engines": list(engines), "results": [], "summary": {},
              "failure_records": []}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for engine in engines:
                for i, c in enumerate(cases):
                    pdf = pdf_dir / f"{c['id']}.pdf"
                    store = Store(Path(tmp) / engine)
                    jid = store.create(pdf.name, pdf.read_bytes())
                    old_engine, old_align = os.environ.get("MDIA_OCR_ENGINE"), os.environ.get("MDIA_PADDLE_WORD_ALIGN")
                    try:
                        os.environ["MDIA_OCR_ENGINE"] = engine
                        os.environ["MDIA_PADDLE_WORD_ALIGN"] = "0"
                        result = process_job(store, jid, ocr_mode="force")
                    finally:
                        if old_engine is None: os.environ.pop("MDIA_OCR_ENGINE", None)
                        else: os.environ["MDIA_OCR_ENGINE"] = old_engine
                        if old_align is None: os.environ.pop("MDIA_PADDLE_WORD_ALIGN", None)
                        else: os.environ["MDIA_PADDLE_WORD_ALIGN"] = old_align
                    flags = []
                    for fp in store.path(jid, "pages").glob("*.json"):
                        flags.append(json.loads(fp.read_text("utf-8")).get("flags", {}))
                    record = score_record(c, result, engine, flags)
                    if result is None or record["page_failures"]:
                        record["runtime_error"] = store.status(jid).get("error", "page failed")
                        report["failure_records"].append(record)
                    if engine == "paddle_arabic" and result and not record["real_paddle_detected"]:
                        raise RuntimeError(f"PaddleOCR not actually invoked: {c['id']}")
                    report["results"].append(record)
                    print(f"{engine} [{i+1}/{len(cases)}] {c['id']}: "
                          f"{record['matched']}/{record['total']} fields, "
                          f"{record['matched_item_names']}/{len(c['rows'])} items", flush=True)
        for eng in engines:
            group = [x for x in report["results"] if x["model"] == eng]
            s = report["summary"][eng] = {
                "documents": len(group), "matched": sum(x["matched"] for x in group),
                "expected": sum(x["total"] for x in group),
                "evidence": sum(x["with_evidence"] for x in group),
                "expected_items": sum(x["expected_item_rows"] for x in group),
                "matched_item_names": sum(x["matched_item_names"] for x in group),
                "extra_item_rows": sum(x["extra_item_rows"] for x in group),
                "failures": sum(bool(x.get("runtime_error")) for x in group),
            }
        layouts = defaultdict(dict)
        for eng in engines:
            for layout in LAYOUTS:
                subset = [r for r in report["results"] if r["model"] == eng and r["layout"] == layout]
                layouts[layout][eng] = {
                    "matched": sum(r["matched"] for r in subset),
                    "expected": sum(r["total"] for r in subset),
                    "evidence": sum(r["with_evidence"] for r in subset),
                    "docs": len(subset),
                }
        report["by_layout"] = dict(layouts)
        report["status"] = "completed_real_ocr" if len(report["results"]) == len(cases)*len(engines) else "incomplete"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        (output_dir / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        print("STATUS:", report["status"], "OUT:", output_dir, flush=True)
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", default="results/invoice_benchmark60")
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--shards", type=int, default=3)
    p.add_argument("--engines", nargs="+", choices=("tesseract", "paddle_arabic"),
                   default=("tesseract", "paddle_arabic"))
    cfg = p.parse_args()
    if cfg.shards <= 0 or not (0 <= cfg.shard < cfg.shards):
        raise SystemExit("invalid shard")
    run(cfg.output_dir, cfg.shard, cfg.shards, cfg.engines)
