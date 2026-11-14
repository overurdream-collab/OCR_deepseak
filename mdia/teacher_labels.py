"""Offline, fail-closed selection of teacher-assisted OCR training labels.

This module never calls an external service and never treats teacher text as truth.
Only exact ground-truth values are eligible for training; ambiguous or incomplete
teacher responses are rejected. All source inputs must be synthetic.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


class TeacherLabelError(ValueError):
    pass


def normalized(text: str) -> str:
    return " ".join(str(text).casefold().split())


def page_texts(response: dict) -> list[str]:
    """Validate a saved DeepSeek OCR response, including page completion."""
    if response.get("object") != "ocr.result":
        raise TeacherLabelError("Invalid OCR response object")
    pages = response.get("pages")
    if not isinstance(pages, list) or not pages:
        raise TeacherLabelError("No OCR pages")
    if response.get("page_count") != len(pages):
        raise TeacherLabelError("Page count mismatch")
    texts = []
    for index, page in enumerate(pages):
        if page.get("index") != index or page.get("finish_reason") != "stop":
            raise TeacherLabelError("Nonsequential or truncated OCR page")
        if not isinstance(page.get("text"), str) or not page["text"].strip():
            raise TeacherLabelError("Empty OCR page")
        texts.append(page["text"])
    return texts


def make_manifest(source: Path, truth: dict, teacher: dict, paddle_text: str) -> dict:
    """Return approved exact-value labels; never infer a missing field.

    Ground truth must be provided from a trusted synthetic fixture. This is a
    *candidate manifest*, not a ready-to-train image/text crop dataset.
    """
    if not source.is_file() or source.suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg"}:
        raise TeacherLabelError("Missing or unsupported synthetic source")
    if not truth.get("synthetic") is True:
        raise TeacherLabelError("Only explicitly synthetic fixtures are allowed")
    fields = truth.get("fields")
    if not isinstance(fields, dict) or not fields:
        raise TeacherLabelError("Ground truth fields required")
    raw = "\n".join(page_texts(teacher))
    approved, rejected = [], []
    for key, value in sorted(fields.items()):
        if not isinstance(key, str) or not isinstance(value, str) or not value.strip():
            raise TeacherLabelError("Ground truth must map field names to nonempty strings")
        # Exact substring presence is a discovery aid only, not field-to-row evidence.
        present_teacher = normalized(value) in normalized(raw)
        present_paddle = normalized(value) in normalized(paddle_text)
        item = {"field": key, "value": value, "teacher_contains": present_teacher,
                "paddle_contains": present_paddle}
        if present_teacher:
            approved.append(item)
        else:
            rejected.append(item)
    return {
        "schema": "mdia.teacher-candidates.v1",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "synthetic": True,
        "status": "CANDIDATES_ONLY_NOT_TRAINING_READY",
        "approved_exact_truth_candidates": approved,
        "teacher_missing_truth": rejected,
        "training_ready": False,
        "notes": "Requires source crop, row association, geometry verification and held-out evaluation."
    }


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Offline DeepSeek teacher-label candidate gate")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--teacher-json", type=Path, required=True)
    parser.add_argument("--paddle-text", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    truth = json.loads(args.truth.read_text(encoding="utf-8"))
    teacher = json.loads(args.teacher_json.read_text(encoding="utf-8"))
    result = make_manifest(args.source, truth, teacher,
                           args.paddle_text.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Candidate truth values: {len(result['approved_exact_truth_candidates'])}; "
          f"missing from teacher: {len(result['teacher_missing_truth'])}; "
          "training_ready=False")


if __name__ == "__main__":
    main()
