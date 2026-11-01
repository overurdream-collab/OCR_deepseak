"""Review-only gate for PP-StructureV3 table HTML; never alter financial data.

Consumes saved PP-StructureV3 JSON (table_res_list[*].pred_html).
This is NOT a source locator, invoice parser or automatic OCR engine switch.
OCR model inference must run in an isolated environment.
"""

import argparse
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import unicodedata


class InvalidTable(ValueError):
    """Table cannot safely be converted to aligned row suggestions."""


class _TableHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.active_row = None
        self.active_cell = None
        self.in_table = 0
        self.unsafe = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table += 1
            if self.in_table > 1:
                self.unsafe.append("nested_table")
        if not self.in_table:
            return
        if tag == "tr":
            if self.active_row is not None:
                self.unsafe.append("overlapping_rows")
            self.active_row = []
        elif tag in ("td", "th"):
            if self.active_cell is not None or self.active_row is None:
                self.unsafe.append("misnested_cell")
            attributes = dict(attrs)
            if attributes.get("rowspan", "1") != "1" or attributes.get("colspan", "1") != "1":
                self.unsafe.append("spanning_cell")
            self.active_cell = []

    def handle_data(self, data):
        if self.active_cell is not None:
            self.active_cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.active_cell is not None:
            if self.active_row is not None:
                self.active_row.append("".join(self.active_cell).strip())
            self.active_cell = None
        elif tag == "tr" and self.active_row is not None:
            if self.active_cell is not None:
                self.unsafe.append("unclosed_cell")
            self.rows.append(self.active_row)
            self.active_row = None
        elif tag == "table":
            self.in_table = max(0, self.in_table - 1)


def parse_html(html):
    if not isinstance(html, str) or not html.strip():
        raise InvalidTable("missing table HTML")
    parser = _TableHTML()
    parser.feed(html)
    parser.close()
    if parser.unsafe or parser.in_table or parser.active_cell is not None or parser.active_row is not None:
        raise InvalidTable("unsafe HTML structure: " + ",".join(sorted(set(parser.unsafe or ["unclosed_structure"]))))
    if not parser.rows or any(not row for row in parser.rows):
        raise InvalidTable("empty table row")
    width = len(parser.rows[0])
    if any(len(row) != width for row in parser.rows):
        raise InvalidTable("unequal row lengths; column association ambiguous")
    return parser.rows


def exact_decimal(raw):
    """Arithmetic-check observed text only; never overwrite OCR source values."""
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    digits = []
    for ch in s:
        if ch.isdecimal():
            digits.append(str(unicodedata.decimal(ch)))
        elif ch in ".٫-,٬":
            digits.append(ch)
        else:
            return None
    s = "".join(digits)
    if s.count("-") > 1 or ("-" in s and not s.startswith("-")):
        return None
    if "٬" in s and "." in s or "٬" in s and "٫" in s:
        return None
    if "٬" in s or "," in s or s.count(".") > 1 or s.count("٫") > 1 or ("." in s and "٫" in s):
        return None
    s = s.replace("٫", ".")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", s):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _source_json(source):
    if not isinstance(source, dict):
        raise InvalidTable("source must be a JSON object")
    return source.get("res", source)


def review_table(source, columns, first_data_row=0):
    """Return review suggestions; never accepted medical/financial values."""
    data = _source_json(source)
    table_results = data.get("table_res_list")
    if not isinstance(table_results, list) or not table_results:
        raise InvalidTable("no table_res_list (table region not detected)")
    if not isinstance(columns, dict) or set(columns) != {"name", "qty", "unit_price", "total"}:
        raise InvalidTable("explicit name/qty/unit_price/total mapping required")
    if any(type(i) is not int or i < 0 for i in columns.values()) or len(set(columns.values())) != 4:
        raise InvalidTable("column indices must be distinct nonnegative integers")
    if type(first_data_row) is not int or first_data_row < 0:
        raise InvalidTable("invalid first_data_row")

    suggestions, problems = [], []
    for table_index, table in enumerate(table_results):
        try:
            rows = parse_html(table.get("pred_html"))
        except (InvalidTable, TypeError, AttributeError) as exc:
            problems.append({"table": table_index, "reason": "invalid_table", "detail": str(exc)})
            continue
        if max(columns.values()) >= len(rows[0]):
            problems.append({"table": table_index, "reason": "missing_mapped_column"})
            continue
        if first_data_row >= len(rows):
            problems.append({"table": table_index, "reason": "no_data_rows"})
            continue
        for row_index, cells in enumerate(rows[first_data_row:], start=first_data_row):
            picked = {key: cells[column] for key, column in columns.items()}
            reasons = ["source_geometry_not_verified", "human_review_required"]
            if any(not text for text in picked.values()):
                reasons.append("missing_cell")
            q, u, total = (exact_decimal(picked[key]) for key in ("qty", "unit_price", "total"))
            if any(x is None for x in (q, u, total)):
                reasons.append("ambiguous_or_unreadable_number")
            elif q <= 0 or u < 0 or total < 0:
                reasons.append("unexpected_negative_or_zero")
            elif q * u != total:
                reasons.append("printed_arithmetic_mismatch")
            suggestions.append({
                "table_index": table_index,
                "row_index": row_index,
                "raw_cells": picked,
                "matched_original_word_boxes": False,
                "review_reasons": reasons,
                "verification": "needs_review",
            })
    return {
        "status": "BLOCKED_FOR_AUTOMATIC_PROMOTION",
        "source": "PP-StructureV3 table_res_list/pred_html",
        "synthetic_only_trial": True,
        "financial_values_modified": False,
        "verified_source_boxes": 0,
        "suggestions": suggestions,
        "problems": problems,
        "warning": "Rows and arithmetic are only visual/OCR suggestions; no original-page evidence geometry was qualified.",
    }


def _columns(value):
    try:
        mapping = dict(part.split("=", 1) for part in value.split(","))
        return {key: int(val) for key, val in mapping.items()}
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError("use name=3,qty=2,unit_price=1,total=0") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Saved PP-StructureV3 JSON")
    parser.add_argument("--columns", type=_columns, required=True,
                        help="Explicit left-to-right column map, e.g. name=3,qty=2,unit_price=1,total=0")
    parser.add_argument("--first-data-row", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = review_table(json.loads(args.input.read_text(encoding="utf-8")),
                              args.columns, args.first_data_row)
    except (OSError, UnicodeError, json.JSONDecodeError, InvalidTable) as exc:
        print(json.dumps({"status": "INVALID_INPUT", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
