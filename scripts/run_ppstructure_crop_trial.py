"""Isolated, opt-in PP-StructureV3 cropped-table experiment (not MDIA runtime).

Run only with locally generated synthetic images. Models may auto-download;
never feed identifiable patient images to a shared CI workflow.
"""
import argparse
import json
from pathlib import Path
import sys


def build_pipeline(factory):
    """Disable table orientation explicitly; it corrupted Eastern-digit scans."""
    return factory(
        device="cpu", use_doc_orientation_classify=False,
        use_doc_unwarping=False, use_textline_orientation=False,
        use_table_orientation_classify=False,
        use_formula_recognition=False,
    )


def extract_json(pipeline, path):
    """Preserve pipeline source JSON, rather than making up word locators."""
    results = []
    for item in pipeline.predict(str(path)):
        payload = item.json
        if not isinstance(payload, dict):
            raise ValueError("PP-StructureV3 returned non-dict result")
        results.append(payload)
    if len(results) != 1:
        raise ValueError("expected exactly one cropped image result")
    return results[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="One local SYNTHETIC cropped table PNG/JPEG")
    parser.add_argument("--output", required=True, type=Path, help="Local OCR result JSON")
    args = parser.parse_args(argv)
    if args.input.suffix.lower() not in (".png", ".jpg", ".jpeg") or not args.input.is_file():
        parser.error("input must be a real local cropped PNG/JPEG")
    if args.output.exists():
        parser.error("output already exists; do not overwrite evidence")
    try:
        from paddleocr import PPStructureV3  # optional heavy dependency
        pipeline = build_pipeline(PPStructureV3)
        result = extract_json(pipeline, args.input)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"ISOLATED_TRIAL_FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print("SAVED_REVIEW_ONLY_JSON (no financial fields approved)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
