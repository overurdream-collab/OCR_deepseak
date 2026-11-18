"""Local command-line proof of concept: structured source audit or MDIA review.

Never publishes, sends invoices, or authorizes payments.
Usage:
  python -m invoice_audit.cli structured --po po.json --grn grn.json --invoice invoice.json
  python -m invoice_audit.cli mdia-review --pdf original.pdf --result mdia-result.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .mdia_bridge import prepare_mdia_review_json
from .source import audit_json_sources
from .report import render_html


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Evidence-first invoice audit (no payment approval)")
    commands = parser.add_subparsers(dest="command", required=True)
    structured = commands.add_parser("structured", help="audit three explicitly structured JSON sources")
    for name in ("po", "grn", "invoice"):
        structured.add_argument("--" + name, required=True, type=Path)
    review = commands.add_parser("mdia-review", help="prepare MDIA OCR output for manual review")
    review.add_argument("--pdf", required=True, type=Path)
    review.add_argument("--result", required=True, type=Path)
    for command in (structured, review):
        command.add_argument("--html-out", type=Path, help="write a read-only local HTML report")
    args = parser.parse_args(argv)
    try:
        if args.command == "structured":
            report = audit_json_sources(args.po.read_bytes(), args.grn.read_bytes(),
                                        args.invoice.read_bytes())
        else:
            report = prepare_mdia_review_json(args.pdf.read_bytes(), args.result.read_bytes())
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        report = {"status": "UNVERIFIABLE", "approval": False, "reasons": [str(exc)]}
    if args.html_out is not None:
        try:
            args.html_out.write_text(render_html(report), encoding="utf-8")
        except (OSError, ValueError) as exc:
            print(f"unable to write report: {exc}", file=sys.stderr)
            return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report.get("status") in ("VERIFIED_MATCH", "VERIFIED_EXCEPTION") else 2


if __name__ == "__main__":
    sys.exit(main())
