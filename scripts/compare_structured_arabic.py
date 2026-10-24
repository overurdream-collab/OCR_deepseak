"""Compare OCR engines through MDIA structured extraction on SYNTHETIC Arabic PDFs.

Metrics: strict fields + SAME-ROW financial associations + evidence-link presence.
Paddle is never silently substituted with Tesseract. Its word positions are
estimated, not independently verified geometry.
"""
import argparse
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path

from mdia.pipeline import process_job
from mdia.store import Store
from scripts.compare_arabic_ocr import prepare

GT = {
    "invoice_shaped.pdf": {"type": "hospital_invoice", "patient": "خالد يوسف",
        "number": "INV-4004", "total": 1401.0,
        "items": [("كشف استشاري", 1, 1250, 1250), ("تحليل دم شامل", 2, 75.5, 151)]},
    "invoice_visual.pdf": {"type": "hospital_invoice", "patient": "خالد يوسف",
        "number": "INV-4004", "total": 1401.0,
        "items": [("كشف استشاري", 1, 1250, 1250), ("تحليل دم شامل", 2, 75.5, 151)]},
    "prescription_shaped.pdf": {"type": "prescription", "patient": "سارة عمر",
        "medicines": [("أموكسيسيلين", "500"), ("باراسيتامول", "500")]},
}


def norm(x):
    s = unicodedata.normalize("NFKC", str(x or ""))
    s = s.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    return re.sub(r"\s+", " ", re.sub("[\u061c\u064b-\u065f\u0670\u0640\u200e\u200f]", "", s)).strip().lower()


def val(f):
    return f.get("value") if isinstance(f, dict) else None


def same(expected, got):
    if isinstance(expected, (int, float)):
        try:
            return got is not None and abs(float(expected) - float(got)) <= .005
        except (TypeError, ValueError):
            return False
    return norm(expected) == norm(got)


def valid_evidence(f, doc):
    if not isinstance(f, dict) or not f.get("evidence_id"):
        return False
    es = [e for e in doc.get("evidence", []) if e.get("id") == f["evidence_id"]]
    if len(es) != 1:
        return False
    e, = es
    b = e.get("bbox")
    return (f.get("page") == e.get("page") and isinstance(b, list) and len(b) == 4
            and all(isinstance(x, (int, float)) and 0 <= x <= 1 for x in b)
            and b[0] < b[2] and b[1] < b[3] and bool(str(e.get("text") or "").strip()))


def row_by_name(rows, key, expected):
    for r in rows:
        name = re.sub(r"^\d+[.\-:]?\s*", "", norm(val(r.get(key))))
        if name == norm(expected):
            return r
    return {}


def evaluate(filename, result, engine, flags):
    truth = GT[filename]
    docs = result.get("documents", []) if result else []
    doc = next((d for d in docs if d.get("document_type") == truth["type"]), docs[0] if docs else {})
    checks = []

    def check(label, expected, f, numbered=False):
        got = val(f)
        compared = re.sub(r"^\d+[.\-:]?\s*", "", norm(got)) if numbered else got
        match = same(expected, compared)
        evidence = match and valid_evidence(f, doc)
        checks.append({"field": label, "expected": expected, "actual": got,
            "match": match, "evidence_link_present": bool(evidence),
            "noninterpolated_word_box_available": bool(evidence and engine != "paddle_arabic")})

    check("patient.name", truth["patient"], doc.get("patient", {}).get("name"))
    checks.append({"field": "document_type", "expected": truth["type"],
        "actual": doc.get("document_type"), "match": doc.get("document_type") == truth["type"],
        "evidence_link_present": False, "noninterpolated_word_box_available": False})

    if "items" in truth:
        invoice = (doc.get("invoices") or [{}])[0]
        check("invoice.number", truth["number"], invoice.get("invoice_number"))
        check("invoice.total", truth["total"], invoice.get("invoice_total"))
        for i, (name, qty, price, amount) in enumerate(truth["items"], 1):
            row = row_by_name(doc.get("invoice_items", []), "service_name", name)
            check(f"items.{i}.name", name, row.get("service_name"), numbered=True)
            check(f"items.{i}.quantity", qty, row.get("quantity"))
            check(f"items.{i}.unit_price", price, row.get("unit_price"))
            check(f"items.{i}.line_total", amount, row.get("line_total"))
    else:
        for i, (name, strength) in enumerate(truth["medicines"], 1):
            row = row_by_name(doc.get("medications", []), "brand_name", name)
            check(f"medications.{i}.name", name, row.get("brand_name"))
            f = row.get("strength")
            match = bool(val(f) and re.search(r"(?<!\d)500(?!\d)", norm(val(f))))
            evidence = match and valid_evidence(f, doc)
            checks.append({"field": f"medications.{i}.strength",
                "expected": strength, "actual": val(f), "match": match,
                "evidence_link_present": bool(evidence),
                "noninterpolated_word_box_available": bool(evidence and engine != "paddle_arabic")})

    failures = [p for p in (result or {}).get("page_info", [])
                if any(w.get("kind") == "page_failed" for w in p.get("warnings", []))]
    return {"pdf": filename, "actual_document_type": doc.get("document_type"),
        "pipeline_status": (result or {}).get("processing_status", "failed"),
        "recognized_records": {"invoice_items": len(doc.get("invoice_items", [])),
            "medications": len(doc.get("medications", []))},
        "matched_fields": sum(c["match"] for c in checks),
        "total_fields": len(checks),
        "evidence_links_on_matching_values": sum(c["evidence_link_present"] for c in checks),
        "noninterpolated_word_boxes": sum(c["noninterpolated_word_box_available"] for c in checks),
        "paddle_model_used": any(f.get("ocr_engine") == "paddleocr-v5-arabic" for f in flags),
        "paddle_review_warning": any(w.get("kind") == "paddle_line_geometry_only" for w in doc.get("warnings", [])),
        "paddle_human_review": any("paddle_line_geometry_only" in r.get("reasons", [])
                                    for r in doc.get("requires_human_review", [])),
        "page_failures": failures, "checks": checks}


def run(output, engines=("tesseract", "paddle_arabic")):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {"status": "incomplete", "source": "synthetic_generated",
        "metric": "30 structured field checks across three PDFs, including same-row association",
        "engines": list(engines), "samples": [], "summaries": {}}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        prepare(root / "pdf")
        try:
            for engine in engines:
                rows = []
                for filename in GT:
                    pdf = root / "pdf" / filename
                    store = Store(root / "jobs" / engine / filename)
                    job = store.create(filename, pdf.read_bytes())
                    previous = os.environ.get("MDIA_OCR_ENGINE")
                    try:
                        os.environ["MDIA_OCR_ENGINE"] = engine
                        result = process_job(store, job, ocr_mode="force")
                    finally:
                        if previous is None:
                            os.environ.pop("MDIA_OCR_ENGINE", None)
                        else:
                            os.environ["MDIA_OCR_ENGINE"] = previous
                    flags = [json.loads(p.read_text("utf-8")).get("flags", {})
                             for p in sorted(store.path(job, "pages").glob("*.json"))]
                    r = evaluate(filename, result, engine, flags)
                    r.update({"engine": engine, "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest()})
                    if result is None or r["page_failures"]:
                        raise RuntimeError(f"{engine}/{filename} failed: {r['page_failures'] or store.status(job)}")
                    if engine == "paddle_arabic" and not (
                        r["paddle_model_used"] and r["paddle_review_warning"] and r["paddle_human_review"]
                    ):
                        raise RuntimeError(f"{engine}/{filename} did not execute Paddle or protect geometry review")
                    report["samples"].append(r)
                    rows.append(r)
                    print(engine, filename, f"{r['matched_fields']}/{r['total_fields']} fields")
                report["summaries"][engine] = {
                    "matched_fields": sum(x["matched_fields"] for x in rows),
                    "total_fields": sum(x["total_fields"] for x in rows),
                    "evidence_links_on_matching_values": sum(x["evidence_links_on_matching_values"] for x in rows),
                    "noninterpolated_word_boxes": sum(x["noninterpolated_word_boxes"] for x in rows),
                    "documents_tested": len(rows),
                }
            report["status"] = "executed_requested_engines"
        except Exception as exc:
            report["status"] = "failed"
            report["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print("Structured benchmark:", report["status"], output)
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="results/arabic_structured_comparison.json")
    p.add_argument("--engines", nargs="+", choices=["tesseract", "paddle_arabic"],
                   default=["tesseract", "paddle_arabic"])
    opts = p.parse_args()
    run(opts.output, opts.engines)
