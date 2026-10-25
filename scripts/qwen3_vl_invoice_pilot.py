"""Qwen3-VL-2B-Instruct *REAL vision* pilot on synthetic invoice PDF images.

CPU, official Q4_K_M language GGUF + official Q8_0 vision projector (Apache 2.0).
Uses llama.cpp locally; no external inference APIs; model weights are public.
No changes to MDIA OCR, pricing, patient data or the production pathway.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

from scripts.ai_table_model_pilot import generate_pdf, render_preview
from scripts.benchmark_invoice300 import new_case

MODEL_REPO = "Qwen/Qwen3-VL-2B-Instruct-GGUF"
MODEL_FILE = "Qwen3VL-2B-Instruct-Q4_K_M.gguf"
PROJECTOR_FILE = "mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf"
VERSION = "MDIA-QWEN3-VL-SYNTHETIC-PILOT-01"
# Cases originate from benchmark-300. This small subset is a pilot, NOT holdout.
CASES = (
    ("ar_shaped", 14),  # Arabic reshaped scan, blur
    ("ar_visual", 17),  # Arabic visually ordered, JPEG artifacts
    ("ar_mixed", 16),   # bilingual low contrast
    ("ar_visual", 15),  # skew
    ("ar_shaped", 18),  # PDF text layer rendered visually
    ("ar_mixed", 14),   # bilingual blurred
    ("en_standard", 14),
    ("en_reordered", 17),
)

PROMPT = """Inspect this image of a SYNTHETIC medical invoice. Read only the image.
استخرج البيانات المطبوعة في هذه الفاتورة الطبية، مع المحافظة على النص العربي والأرقام كما تظهر.
Return ONLY one JSON object without markdown:
{"patient_name":null,"invoice_number":null,"invoice_total":null,
"items":[{"description":null,"quantity":null,"unit_price":null,"line_total":null}]}
Rules:
- Use one item per printed invoice charge row; NEVER include table header, subtotal,
  tax, discount, summary, currency, explanatory note, or fabricated item as a charge.
- Extract patient name, invoice number and final invoice total only if visible.
- For every item use the printed quantity/unit price/line total, NOT calculated values.
- Retain Arabic item names exactly as printed; English names exactly as printed.
- Numeric amounts may be JSON strings or numbers. If unclear, use null.
- Invoice may be right-to-left (Arabic). Match every item to numbers on its own row.
- Never infer unreadable patient identifiers, quantities, prices or missing amounts.
- Do not output explanatory text, only JSON.
"""


def decimal_number(v):
    if isinstance(v, bool) or v is None:
        return None
    t = str(v).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬", "01234567890123456789.,")).strip()
    t = t.replace(",", "").replace(" ", "")
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", t):
        return None
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def norm_text(v):
    import unicodedata
    if v is None:
        return ""
    t = unicodedata.normalize("NFKC", str(v))
    t = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", t)
    t = t.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")).casefold()
    return re.sub(r"\s+", " ", t).strip(" \n\t.:،")


def same_value(expected, actual, numeric=False):
    if numeric:
        left, right = decimal_number(expected), decimal_number(actual)
        return left is not None and right is not None and left == right
    return bool(actual is not None and norm_text(expected) == norm_text(actual))


def extract_json(raw):
    """Try balanced JSON objects in model stdout, no guessing or key fabrication."""
    decoder = json.JSONDecoder()
    if not isinstance(raw, str):
        raise ValueError("response is not text")
    candidates = []
    for start in (m.start() for m in re.finditer(r"\{", raw)):
        try:
            candidate, _ = decoder.raw_decode(raw[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and "items" in candidate and "invoice_number" in candidate:
            if not isinstance(candidate["items"], list):
                raise ValueError("model returned non-list invoice items")
            candidates.append(candidate)
    if candidates:
        return candidates[-1]
    raise ValueError("no valid invoice JSON object in model output")


def score_invoice(truth, data):
    """Strict exact per-field score; bad/extra rows and arithmetic reported separately."""
    expected_rows = truth["rows"]
    proposed = data.get("items")
    if not isinstance(proposed, list) or len(proposed) > 70:
        raise ValueError("malformed or unreasonable invoice item list")
    checks = []
    def check(field, expected, actual, numeric=False):
        checks.append({"field": field, "expected": expected,
                       "actual": actual, "match": same_value(expected, actual, numeric)})
    check("patient.name", truth["patient"], data.get("patient_name"))
    check("invoice.number", truth["invoice_number"], data.get("invoice_number"))
    check("invoice.total", truth["invoice_total"], data.get("invoice_total"), True)
    used = set()
    no_match = []
    for pos, row in enumerate(expected_rows, 1):
        candidates = [i for i, p in enumerate(proposed)
                      if i not in used and isinstance(p, dict) and
                      same_value(row["name"], p.get("description"))]
        if len(candidates) == 1:
            idx = candidates[0]
            used.add(idx)
            selected = proposed[idx]
        else:
            selected = {}
            no_match.append({"expected_index": pos, "description": row["name"],
                             "candidate_count": len(candidates)})
        check(f"item.{pos}.description", row["name"], selected.get("description"))
        check(f"item.{pos}.quantity", row["qty"], selected.get("quantity"), True)
        check(f"item.{pos}.unit_price", row["price"], selected.get("unit_price"), True)
        check(f"item.{pos}.line_total", row["total"], selected.get("line_total"), True)
    extra = [x for i, x in enumerate(proposed) if i not in used]
    inconsistent = []
    for i, row in enumerate(proposed):
        if not isinstance(row, dict):
            inconsistent.append({"index": i, "problem": "non-dict item"})
            continue
        q, p, total = [decimal_number(row.get(x)) for x in ("quantity", "unit_price", "line_total")]
        if q is not None and p is not None and total is not None and q*p != total:
            inconsistent.append({"index": i, "problem": "qty_times_price_not_line_total",
                                 "quantity": str(q), "unit_price": str(p), "line_total": str(total)})
    return {"correct": sum(x["match"] for x in checks), "expected": len(checks),
            "fields": checks, "expected_rows": len(expected_rows),
            "matched_item_names": len(used), "extra_rows": len(extra),
            "unmatched_rows": no_match, "extra_items": extra[:20],
            "inconsistent_predicted_rows": inconsistent,
            "needs_human_review": True, "financial_values_auto_applied": 0,
            "source_word_boxes_verified": False}


def run_one(cli, model, projector, case, dest, context=4096, max_tokens=500, timeout=660):
    case_id = case["id"]
    pdf = dest / "pdf" / (case_id + ".pdf")
    image = dest / "png" / (case_id + ".png")
    pdf.parent.mkdir(parents=True, exist_ok=True)
    image.parent.mkdir(parents=True, exist_ok=True)
    generate_pdf(pdf, case)
    rgb = render_preview(pdf)
    rgb.thumbnail((1150, 1650))
    rgb.save(image, optimize=True)
    cmd = [
        str(cli), "-m", str(model), "--mmproj", str(projector),
        "--image", str(image), "-p", PROMPT, "-st", "-n", str(max_tokens),
        "-c", str(context), "-t", "3", "-ngl", "0",
        "--no-mmproj-offload", "--temp", "0", "--simple-io", "--no-display-prompt",
    ]
    start = time.monotonic()
    result = {"id": case_id, "layout": case["layout"], "representation": case["representation"],
              "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
              "input_image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
              "model": MODEL_REPO, "quantization": "Q4_K_M+mmproj-Q8_0",
              "expected_items": len(case["rows"]), "outcome": "pending",
              "score": None}
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=timeout, check=False, errors="replace")
        (dest / "responses").mkdir(exist_ok=True)
        (dest / "responses" / (case_id + ".stdout.txt")).write_text(
            completed.stdout, encoding="utf-8")
        (dest / "responses" / (case_id + ".stderr.txt")).write_text(
            completed.stderr[-25000:], encoding="utf-8")
        result["exit_code"] = completed.returncode
        result["stderr_tail"] = completed.stderr[-1500:]
        if completed.returncode != 0:
            result["outcome"] = "runtime_failure"
            return result
        parsed = extract_json(completed.stdout)
        result["prediction"] = parsed
        result["score"] = score_invoice(case, parsed)
        result["outcome"] = "parsed_and_scored"
    except subprocess.TimeoutExpired as ex:
        result["outcome"] = "timeout"
        result["error"] = str(ex)
    except (ValueError, TypeError) as ex:
        result["outcome"] = "invalid_model_response"
        result["error"] = str(ex)
    finally:
        result["elapsed_sec"] = round(time.monotonic() - start, 2)
    return result


def run(output_dir, cli, model, projector, shard=0, shards=2, max_cases=4):
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    all_items = [new_case(layout, i) for layout, i in CASES[:max_cases]]
    chosen = [v for n, v in enumerate(all_items) if n % shards == shard]
    report = {"status": "incomplete", "version": VERSION,
              "model_id": MODEL_REPO, "weight_file": MODEL_FILE,
              "projector_file": PROJECTOR_FILE,
              "shard": shard, "shards": shards, "cases_planned": len(chosen),
              "data_policy": "100_percent_synthetic_local_inference",
              "results": []}
    try:
        for i, case in enumerate(chosen, 1):
            result = run_one(cli, model, projector, case, root)
            report["results"].append(result)
            s = result.get("score") or {}
            print(f"QWEN {i}/{len(chosen)} {case['id']}: {result['outcome']} "
                  f"fields={s.get('correct','?')}/{s.get('expected','?')} "
                  f"seconds={result['elapsed_sec']}", flush=True)
        report["status"] = ("completed_with_failures" if any(r["outcome"] != "parsed_and_scored"
                         for r in report["results"]) else "completed_scored")
    except Exception as ex:
        report["status"] = "harness_failure"
        report["error"] = f"{type(ex).__name__}: {ex}"
        raise
    finally:
        report["summary"] = {
            "attempted": len(report["results"]),
            "parsed": sum(r["outcome"] == "parsed_and_scored" for r in report["results"]),
            "failed": sum(r["outcome"] != "parsed_and_scored" for r in report["results"]),
            "field_matches": sum((r.get("score") or {}).get("correct", 0) for r in report["results"]),
            "scored_fields": sum((r.get("score") or {}).get("expected", 0) for r in report["results"]),
            "requested_cases": len(chosen), "changed_production_fields": 0}
        (root / "qwen3_vl_results.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        print("QWEN FINAL", report["status"], report["summary"], flush=True)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--cli", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--projector", required=True)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=2)
    parser.add_argument("--max-cases", type=int, default=4)
    a = parser.parse_args()
    if a.shards < 1 or not (0 <= a.shard < a.shards) or not 1 <= a.max_cases <= len(CASES):
        raise SystemExit("invalid shard")
    run(a.output_dir, a.cli, a.model, a.projector, a.shard, a.shards, a.max_cases)


if __name__ == "__main__":
    main()
