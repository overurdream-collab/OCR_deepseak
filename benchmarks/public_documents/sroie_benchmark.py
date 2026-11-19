"""Download an independently published SROIE HOLDOUT sample and report OCR text coverage.

No inference from a synthetic invoice. No uploading or committing third-party
document bytes. The benchmark only checks whether a labeled TOTAL string is
visible in raw OCR text, NOT whether the OCR model reliably identified the
correct total field or audited a transaction.

Requires: pip install Pillow pytesseract, installed Tesseract executable.
Run: python -m benchmarks.public_documents.sroie_benchmark --limit 10
"""
from __future__ import annotations

import argparse
import base64
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import time
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

DATASET = "jsdnrs/ICDAR2019-SROIE"
API = "https://datasets-server.huggingface.co"
MAX_IMAGE_BYTES = 6_000_000


def _get_with_retry(url: str, *, max_bytes: int | None = None):
    """Retry transient public dataset gateway failures; never invent test rows."""
    for attempt in range(4):
        try:
            with urlopen(Request(url, headers={"User-Agent": "MDIA-public-benchmark/1.0"}),
                         timeout=40) as response:
                return response.read(max_bytes + 1 if max_bytes is not None else 8_000_001)
        except (HTTPError, URLError, TimeoutError) as exc:
            transient = not isinstance(exc, HTTPError) or exc.code in (429, 500, 502, 503, 504)
            if not transient or attempt == 3:
                raise
            time.sleep(min(2 ** attempt, 8))


def request_json(url: str):
    return json.loads(_get_with_retry(url).decode("utf-8"))


def read_image_from_row(image):
    if not isinstance(image, dict):
        raise ValueError("image metadata is not a dict")
    src = image.get("src")
    if not isinstance(src, str):
        raise ValueError("no image.src returned by dataset service")
    if src.startswith("data:image/") and ";base64," in src:
        data = base64.b64decode(src.split(";base64,", 1)[1], validate=True)
    elif src.startswith("https://huggingface.co/") or src.startswith("https://datasets-server.huggingface.co/"):
        data = _get_with_retry(src, max_bytes=MAX_IMAGE_BYTES)
    else:
        raise ValueError("image src is not on allowlisted HTTPS host or base64 image")
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("image missing or above benchmark size limit")
    return data


def norm_amount(value):
    """Parse ONE printed money token, never concatenate the whole OCR page."""
    token = str(value).strip().replace(" ", "")
    if token.startswith("$"):
        token = token[1:]
    if not re.fullmatch(r"[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?", token):
        return None
    try:
        return Decimal(token.replace(",", ""))
    except InvalidOperation:
        return None


AMOUNT_TOKEN = re.compile(
    r"(?<![0-9])(?:[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)(?![0-9])"
)


def total_token_present(raw_text, printed_total):
    target = norm_amount(printed_total)
    if target is None:
        return False
    return any(norm_amount(token.group(0)) == target
               for token in AMOUNT_TOKEN.finditer(raw_text))


def split_info():
    data = request_json(API + "/splits?" + urlencode({"dataset": DATASET}))
    splits = [entry for entry in data.get("splits", [])
              if entry.get("dataset") == DATASET and entry.get("split") == "test"]
    if not splits:
        raise ValueError("no explicitly named test split; benchmark cannot proceed")
    item = splits[0]
    return item["config"], item["split"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--out", type=Path, default=Path("benchmark-public-report.json"))
    args = parser.parse_args()
    if not 1 <= args.limit <= 30:
        parser.error("limit must be between 1 and 30")
    from PIL import Image, ImageOps
    import pytesseract
    from pytesseract import Output
    from .field_selector import tess_lines, select_total, evaluate_selected
    config, split = split_info()
    rows = request_json(API + "/rows?" + urlencode({
        "dataset": DATASET, "config": config, "split": split,
        "offset": 0, "length": args.limit,
    })).get("rows", [])
    if len(rows) != args.limit:
        raise RuntimeError(f"expected {args.limit} test rows, got {len(rows)}")
    results = []
    for entry in rows:
        idx = entry.get("row_idx")
        row = entry.get("row") or {}
        original = read_image_from_row(row.get("image"))
        with Image.open(BytesIO(original)) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            data = pytesseract.image_to_data(im, lang="eng", config="--psm 6", output_type=Output.DICT)
            lines = tess_lines(data)
            text = "\n".join(line["text"] for line in lines)
            selected = select_total(lines)
        entities = row.get("entities") or {}
        total = entities.get("total") if isinstance(entities, dict) else None
        if not isinstance(total, (str, int, float)) or not str(total).strip():
            raise ValueError(f"row {idx}: no annotated total")
        observed = total_token_present(text, total)
        field_outcome = evaluate_selected(selected, total)
        results.append({
            "row_idx": idx,
            "image_sha256": hashlib.sha256(original).hexdigest(),
            "annotated_total": str(total),
            "raw_ocr_contains_label_total": observed,
            "total_field_selection": field_outcome,
            "selected_total": selected.get("value") if selected["status"] == "candidate" else None,
            "selected_line_id": selected.get("line_id"),
            "selected_line_bbox": selected.get("bbox"),
            "total_field_status": selected["status"],
            "total_field_reason": selected.get("reason"),
            "ocr_chars": len(text),
            "ocr_engine": "tesseract/eng/psm6",
        })
    successes = sum(r["raw_ocr_contains_label_total"] for r in results)
    outcome_counts = {outcome: sum(r["total_field_selection"] == outcome for r in results)
                      for outcome in ("correct", "wrong", "abstained", "invalid_reference")}
    report = {
        "dataset": DATASET, "dataset_split": split, "dataset_config": config,
        "kind": "real_receipt_images_not_supplier_po_grn",
        "evaluation": "raw_ocr_total_token_occurrence_only_not_financial_audit",
        "count": len(results), "raw_ocr_total_token_found": successes,
        "raw_ocr_total_token_missing": len(results) - successes,
        "total_token_occurrence_rate": successes / len(results),
        "field_selection_outcomes": outcome_counts,
        "field_selection_accuracy_over_all_rows": outcome_counts["correct"] / len(results),
        "field_selection_error_over_all_rows": outcome_counts["wrong"] / len(results),
        "field_selection_coverage": (outcome_counts["correct"] + outcome_counts["wrong"]) / len(results),
        "financial_field_acceptance": "FAIL" if outcome_counts["wrong"] or outcome_counts["abstained"] or outcome_counts["invalid_reference"] else "REQUIRES_INDEPENDENT_REVIEW",
        "finance_ready": False,
        "payment_authorized": False,
        "field_evaluation": "strict single-total-line selection with abstention, not authenticated invoice approval",
        "results": results, "financial_match_accuracy": None,
        "invoice_line_accuracy": None, "issuer_authenticity": "not_tested",
        "license": "CC-BY-4.0", "run_timestamp_unix": int(time.time()),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"SROIE TEST holdout, {len(results)} real receipts: raw OCR total visible {successes}/{len(results)}")
    print("Conservative total-field selection:", outcome_counts)
    print("Financial-field acceptance:", report["financial_field_acceptance"], "(no payment authority)")
    print("NOT a three-way matching or business authenticity benchmark.")


if __name__ == "__main__":
    main()
