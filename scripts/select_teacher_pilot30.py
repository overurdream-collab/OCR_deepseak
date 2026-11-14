"""Select a reproducible, stratified 30-case EVALUATION-only pilot.

Uses existing 300-case synthetic holdout metadata, never patient records.
These IDs are forbidden for teacher-student training; the 300-case acceptance
set remains holdout. The script does not render, upload or call an API.
"""
import argparse
import hashlib
import json
from pathlib import Path

from scripts.benchmark_invoice300 import LAYOUTS, all_cases

MODES = ("text", "scan", "blur", "skew", "lowcontrast", "jpeg")
PILOT_INDICES = (10, 11, 12, 13, 14, 15)


def select_cases():
    cases = all_cases()
    selected = [c for c in cases if c["variant"] in PILOT_INDICES]
    # Six layouts x six representations would be 36; choose five modes per layout,
    # rotating omitted mode to cover all six representations overall.
    selected = [
        c for c in selected
        if (c["variant"] - 10) != LAYOUTS.index(c["layout"])
    ]
    assert len(selected) == 30
    assert len({c["id"] for c in selected}) == 30
    assert set(c["layout"] for c in selected) == set(LAYOUTS)
    assert set(c["representation"] for c in selected) == set(MODES)
    return selected


def manifest():
    records = [{
        "case_id": c["id"],
        "layout": c["layout"],
        "representation": c["representation"],
        "pages": c["pages"],
        "currency": c["currency"],
        "case_metadata_sha256": hashlib.sha256(
            json.dumps(c, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
    } for c in select_cases()]
    return {
        "schema": "mdia.teacher-pilot30.v1",
        "purpose": "EVALUATION_ONLY_NOT_FOR_TRAINING",
        "source": "scripts.benchmark_invoice300.all_cases",
        "synthetic": True,
        "count": len(records),
        "cases": records,
        "notice": "Holdout benchmark cases cannot become fine-tuning labels."
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest(), ensure_ascii=False, indent=2), encoding="utf-8")
    print("Selected 30 synthetic evaluation-only cases across six layouts.")


if __name__ == "__main__":
    main()
