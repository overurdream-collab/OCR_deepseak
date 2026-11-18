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

DATASET = "jsdnrs/ICDAR2019-SROIE"
API = "https://datasets-server.huggingface.co"
MAX_IMAGE_BYTES = 6_000_000


def request_json(url: str):
    with urlopen(Request(url, headers={"User-Agent": "MDIA-public-benchmark/1.0"}),
                 timeout=40) as response:
        return json.load(response)


def read_image_from_row(image):
    if not isinstance(image, dict):
        raise ValueError("image metadata is not a dict")
    src = image.get("src")
    if not isinstance(src, str):
        raise ValueError("no image.src returned by dataset service")
    if src.startswith("data:image/") and ";base64," in src:
        data = base64.b64decode(src.split(";base64,", 1)[1], validate=True)
    elif src.startswith("https://huggingface.co/") or src.startswith("https://datasets-server.huggingface.co/"):
        with urlopen(Request(src, headers={"User-Agent": "MDIA-public-benchmark/1.0"}),
                     timeout=40) as response:
            data = response.read(MAX_IMAGE_BYTES + 1)
    else:
        raise ValueError("image src is not on allowlisted HTTPS host or base64 image")
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("image missing or above benchmark size limit")
    return data


def norm_amount(value):
    """Parse ONE printed money token, never concatenate the whole OCR page."""
    token = str(value).strip().replace(" ", "")
    if not re.fullmatch(r"[0-9]{1,3}(?:,[0-9]{3})+(?:\\.[0-9]{1,2})?|[0-9]+(?:\\.[0-9]{1,2})?", token):
        return None
    try:
        return Decimal(token.replace(",", ""))
    except InvalidOperation:
        return None


AMOUNT_TOKEN = re.compile(
    r"(?<![0-9])(?:[0-9]{1,3}(?:,[0-9]{3})+(?:\\.[0-9]{1,2})?|[0-9]+(?:\\.[0-9]{1,2})?)(?![0-9])"
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
            text = pytesseract.image_to_string(im, lang="eng", config="--psm 6")
        entities = row.get("entities") or {}
        total = entities.get("total") if isinstance(entities, dict) else None
        if not isinstance(total, (str, int, float)) or not str(total).strip():
            raise ValueError(f"row {idx}: no annotated total")
        observed = total_token_present(text, total)
        results.append({
            "row_idx": idx,
            "image_sha256": hashlib.sha256(original).hexdigest(),
            "annotated_total": str(total),
            "raw_ocr_contains_label_total": observed,
            "ocr_chars": len(text),
            "ocr_engine": "tesseract/eng/psm6",
        })
    successes = sum(r["raw_ocr_contains_label_total"] for r in results)
    report = {
        "dataset": DATASET, "dataset_split": split, "dataset_config": config,
        "kind": "real_receipt_images_not_supplier_po_grn",
        "evaluation": "raw_ocr_total_token_occurrence_only_not_financial_audit",
        "count": len(results), "raw_ocr_total_token_found": successes,
        "raw_ocr_total_token_missing": len(results) - successes,
        "total_token_occurrence_rate": successes / len(results),
        "results": results, "financial_match_accuracy": None,
        "invoice_line_accuracy": None, "issuer_authenticity": "not_tested",
        "license": "CC-BY-4.0", "run_timestamp_unix": int(time.time()),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"SROIE TEST holdout, {len(results)} real receipts: raw OCR total visible {successes}/{len(results)}")
    print("NOT a three-way matching or business authenticity benchmark.")


if __name__ == "__main__":
    main()
