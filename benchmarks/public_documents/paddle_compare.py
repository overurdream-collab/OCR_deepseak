"""Experimental PaddleOCR 3.x vs Tesseract total-field selector on fixed SROIE test rows.

Network downloads weights on first execution, CPU may be slow. This is
NOT a DeepSeek-OCR result, not a financial audit, and does not make any payment.
Use only the exact same rows and fixed annotation labels as the Tesseract run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode

from .sroie_benchmark import API, DATASET, request_json, read_image_from_row, split_info
from .field_selector import select_total, evaluate_selected, tess_lines


def _paddle_to_lines(image, ocr):
    import numpy as np
    results = ocr.predict(np.asarray(image))
    if len(results) != 1:
        raise ValueError("unexpected PaddleOCR result cardinality")
    result = results[0]
    data = result.json if hasattr(result, "json") else result
    if callable(data):
        data = data()
    if not isinstance(data, dict):
        raise ValueError("unsupported PaddleOCR result")
    data = data.get("res", data)
    texts = data.get("rec_texts")
    boxes = data.get("rec_boxes")
    scores = data.get("rec_scores")
    if texts is None or boxes is None or scores is None:
        raise ValueError("PaddleOCR must provide recognized text, boxes and scores")
    if len(texts) != len(boxes) or len(texts) != len(scores):
        raise ValueError("PaddleOCR text/geometry/score cardinality mismatch")
    lines = []
    for i, (text, box, score) in enumerate(zip(texts, boxes, scores)):
        box = [int(x) for x in box]
        if len(box) != 4:
            raise ValueError("invalid PaddleOCR bounding box")
        lines.append({"line_id": f"paddle-{i}", "text": str(text),
                      "bbox": box, "confidence": float(score)})
    return lines


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--out", type=Path, default=Path("results/ocr-engine-comparison.json"))
    args = parser.parse_args()
    if not 1 <= args.limit <= 10:
        parser.error("limit must be between 1 and 10")
    from PIL import Image, ImageOps
    import pytesseract
    from pytesseract import Output
    from paddleocr import PaddleOCR

    engine = PaddleOCR(lang="en", use_doc_orientation_classify=False,
                       use_doc_unwarping=False, use_textline_orientation=False,
                       enable_mkldnn=False)
    config, split = split_info()
    rows = request_json(API + "/rows?" + urlencode({
        "dataset": DATASET, "config": config, "split": split,
        "offset": 0, "length": args.limit})).get("rows", [])
    if len(rows) != args.limit:
        raise ValueError("test row download incomplete")
    counts = {engine_name: {"correct": 0, "wrong": 0, "abstained": 0, "invalid_reference": 0}
              for engine_name in ("tesseract", "paddleocr")}
    results = []
    for entry in rows:
        row = entry.get("row") or {}
        original = read_image_from_row(row.get("image"))
        with Image.open(BytesIO(original)) as source:
            im = ImageOps.exif_transpose(source).convert("RGB")
            tess = tess_lines(pytesseract.image_to_data(
                im, lang="eng", config="--psm 6", output_type=Output.DICT))
            paddle = _paddle_to_lines(im, engine)
        total = (row.get("entities") or {}).get("total")
        if total is None:
            raise ValueError("missing SROIE annotated total")
        outcomes = {}
        for name, lines in (("tesseract", tess), ("paddleocr", paddle)):
            chosen = select_total(lines)
            result = evaluate_selected(chosen, total)
            counts[name][result] += 1
            outcomes[name] = {
                "status": result,
                "candidate": chosen.get("value") if chosen["status"] == "candidate" else None,
                "selected_line_id": chosen.get("line_id"),
                "selected_line_box": chosen.get("bbox"),
                "evidence_state": "ocr_provisional",
            }
        results.append({"row_idx": entry.get("row_idx"),
                        "image_sha256": hashlib.sha256(original).hexdigest(),
                        "annotated_total": str(total), "engines": outcomes})
    result = {"dataset": DATASET, "split": split, "sample_count": len(results),
              "evaluation": "strict labeled total field selection only",
              "engines": counts, "results": results, "financial_approval": False,
              "deepseek_tested": False, "issuer_authenticity": "not_tested"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print("Same-originals OCR field selector benchmark:", counts)


if __name__ == "__main__":
    main()
