"""Sample original Portuguese invoice/receipt images from public InvoicesReceiptsPT.

No associated labels are available through the imagefolder viewer. This is a
real-image OCR runtime smoke test, NOT an accuracy benchmark or a clean holdout.
Third-party images stay in memory; never commit or re-publish raw documents.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode

from .sroie_benchmark import API, read_image_from_row, request_json

DATASET = "Francisco-Cruz/InvoicesReceiptsPT"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--out", type=Path, default=Path("results/portuguese-sample.json"))
    args = parser.parse_args()
    if not 1 <= args.limit <= 10:
        parser.error("limit must be 1..10")
    from PIL import Image, ImageOps
    import pytesseract
    splits = request_json(API + "/splits?" + urlencode({"dataset": DATASET})).get("splits", [])
    choices = [s for s in splits if s.get("dataset") == DATASET and s.get("split") == "train"]
    if not choices:
        raise ValueError("no public train split found")
    config = choices[0]["config"]
    records = request_json(API + "/rows?" + urlencode({
        "dataset": DATASET, "config": config, "split": "train",
        "offset": 0, "length": args.limit
    })).get("rows", [])
    if len(records) != args.limit:
        raise ValueError("missing sample records")
    result = []
    for entry in records:
        row = entry.get("row") or {}
        data = read_image_from_row(row.get("image"))
        with Image.open(BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            text = pytesseract.image_to_string(im, lang="eng", config="--psm 6")
        result.append({
            "row_idx": entry.get("row_idx"),
            "image_sha256": hashlib.sha256(data).hexdigest(),
            "ocr_has_nonempty_text": bool(text.strip()),
            "ocr_chars": len(text),
        })
    report = {
        "dataset": DATASET, "split": "train",
        "evaluation": "REAL_PUBLIC_IMAGE_OCR_SMOKE_ONLY_NO_LABELS",
        "count": len(result),
        "ocr_nonempty_count": sum(x["ocr_has_nonempty_text"] for x in result),
        "field_accuracy": None, "three_way_audit_accuracy": None,
        "financial_approval": False,
        "results": result,
        "data_rights": "dataset card shows Apache-2.0; verify underlying image rights and privacy",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Portuguese original invoice/receipt images sampled:", len(result),
          "nonempty OCR:", report["ocr_nonempty_count"])
    print("NOT a labeled invoice field accuracy or three-way matching benchmark.")


if __name__ == "__main__":
    main()
