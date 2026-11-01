"""Investigate OCR decimal-point loss on a FIXED list of synthetic invoices.

Opt-in CPU experiment, no runtime change and no real patient data.
Capture original OCR word tokens before any financial-value normalization.
Never convert the result into automatic corrections.
"""
import argparse
import json
import os
import tempfile
from pathlib import Path

from mdia.pipeline import process_job
from mdia.store import Store
from scripts.benchmark_invoice300 import (all_cases, arabic_invoice, scan_pdf,
                                          score_record)


DEFAULT_CASES = ("ar_mixed_26", "ar_shaped_26", "ar_visual_32", "ar_mixed_42")


def classify_field(check):
    if check["matched"]:
        return "correct"
    if check["actual"] is None:
        return "missing"
    if check["field"].endswith((".price", ".total")):
        expected, actual = check["expected"], check["actual"]
        if isinstance(expected, (float, int)) and isinstance(actual, (float, int)) and expected:
            if abs(actual / expected - 100) < 1e-8:
                return "suspected_decimal_separator_loss_100x"
    return "incorrect"


def analyze_case(case, result, flags, page_caches, mode):
    record = score_record(case, result, "paddle_arabic", flags)
    rows = []
    for check in record["checks"]:
        if check["matched"]:
            continue
        rows.append({
            "field": check["field"],
            "expected_synthetic": check["expected"],
            "actual_observed": check["actual"],
            "classification": classify_field(check),
        })
    word_lines = []
    for cache in page_caches:
        words = cache.get("words", [])
        # Original OCR tokens, not guessed reconstructed amounts or values.
        word_lines.append({
            "page": cache["number"],
            "method": cache["method"],
            "ocr_engine": cache.get("flags", {}).get("ocr_engine"),
            "words": [{
                "raw": w.get("text"),
                "x0": w.get("x0"),
                "y0": w.get("y0"),
                "x1": w.get("x1"),
                "y1": w.get("y1"),
                "geometry_source": w.get("geometry_source")
            } for w in words],
        })
    return {
        "id": case["id"], "layout": case["layout"], "representation": case["representation"],
        "mode": mode, "correct": record["matched"], "expected": record["total"],
        "extracted_rows": record["extracted_item_rows"],
        "lost_fields": rows, "ocr_source_words": word_lines,
        "page_failures": record["page_failures"],
    }


def run(cases, output):
    by_id = {case["id"]: case for case in all_cases()}
    if len(set(cases)) != len(cases) or not cases:
        raise ValueError("invalid duplicate/empty case list")
    if any(case not in by_id or not case.startswith("ar_") for case in cases):
        raise ValueError("only known synthetic Arabic cases allowed")
    report = {"status": "incomplete", "synthetic_only": True, "cases": [],
              "no_financial_modifications": True}
    try:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for case_id in cases:
                case = by_id[case_id]
                pdf_dir = root / "pdfs"
                pdf_dir.mkdir(exist_ok=True)
                pdf = pdf_dir / (case_id + ".pdf")
                source = pdf_dir / ("_" + case_id + ".pdf")
                arabic_invoice(source, case)
                if case["representation"] == "text":
                    source.rename(pdf)
                else:
                    scan_pdf(source, pdf, case["representation"], case["variant"])
                    source.unlink()
                for mode in ("original", "image_enhanced"):
                    store = Store(root / mode / case_id)
                    job = store.create(pdf.name, pdf.read_bytes())
                    old = {key: os.environ.get(key) for key in (
                        "MDIA_OCR_ENGINE", "MDIA_OCR_IMAGE_ENHANCE",
                        "MDIA_PADDLE_WORD_ALIGN", "MDIA_STRICT_INVOICE_REVIEW")}
                    try:
                        os.environ["MDIA_OCR_ENGINE"] = "paddle_arabic"
                        os.environ["MDIA_OCR_IMAGE_ENHANCE"] = "1" if mode == "image_enhanced" else "0"
                        os.environ["MDIA_PADDLE_WORD_ALIGN"] = "0"
                        os.environ["MDIA_STRICT_INVOICE_REVIEW"] = "0"
                        result = process_job(store, job, ocr_mode="force")
                    finally:
                        for key, value in old.items():
                            if value is None:
                                os.environ.pop(key, None)
                            else:
                                os.environ[key] = value
                    caches = [json.loads(path.read_text(encoding="utf-8"))
                              for path in sorted(store.path(job, "pages").glob("*.json"))]
                    flags = [cache.get("flags", {}) for cache in caches]
                    if not caches or not any(f.get("ocr_engine") == "paddleocr-v5-arabic" for f in flags):
                        raise RuntimeError("real PaddleOCR did not run for " + case_id)
                    report["cases"].append(analyze_case(case, result, flags, caches, mode))
                    c = report["cases"][-1]
                    print(f'{case_id} {mode}: {c["correct"]}/{c["expected"]} fields', flush=True)
        report["status"] = "completed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="+", default=list(DEFAULT_CASES))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = run(args.cases, args.output)
    return int(result["status"] != "completed")


if __name__ == "__main__":
    raise SystemExit(main())
