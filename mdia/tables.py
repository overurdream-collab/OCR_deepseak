"""Layout-based table understanding (works for text PDFs and OCR output, ruled or unruled).

A header row is recognised from bilingual column names; its word positions define the columns,
and the exact column borders are refined with the empty vertical gaps found in the data rows."""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .kv import find_matches, line_pairs
from .lexicon import COLUMN_TABLE, SECTION_WORDS, TOTAL_IDS
from .model import Line, Page, Word, logical_order
from .textutil import CUR_TOKEN_RE, ar_ratio, has_ar, is_numeric_token, match_key

_STOP_WORDS = {match_key(w) for w in ("signature stamp authorized توقيع ختم المحاسب مدير").split()}
_PAGE_OF = re.compile(r"(?i)(page\s*\d+\s*(of|/)\s*\d+|صفحه\s*\d+\s*(من|/)\s*\d+)")
NUMERIC_COLS = {"qty", "unit_price", "total", "discount", "claimed", "paid", "patient_share", "dispensed", "prescribed"}


@dataclass
class Row:
    line_idxs: List[int]
    cells: Dict[str, List[Word]]
    section: Optional[str] = None
    section_words: List[Word] = field(default_factory=list)
    inherited: bool = False

    @property
    def words(self):
        return [w for ws in self.cells.values() for w in ws]


@dataclass
class Table:
    kind: str                              # invoice | med | lab
    page: int
    header_idx: Optional[int]
    bounds: List[tuple]                    # [(col_id, left, right)] ascending x
    rows: List[Row] = field(default_factory=list)
    line_idxs: set = field(default_factory=set)
    inherited: bool = False
    rtl: bool = False


def _kind(cols):
    if "name" in cols and cols & {"result", "ref_range"}:
        return "lab"
    if cols & {"strength", "dose", "frequency", "duration", "route", "form", "prescribed", "dispensed"}:
        return "med"
    return "invoice"


def header_columns(line: Line):
    """-> {col_id: [Word]} if the line looks like a table header, else None."""
    ms = find_matches([w.key for w in line.words], COLUMN_TABLE)
    cols: Dict[str, List[Word]] = {}
    used = 0
    for m in ms:
        if m.id in cols:
            continue
        cols[m.id] = line.words[m.s:m.e]
        used += m.e - m.s
    if used < 0.6 * len(line.words):
        return None
    ok = ("name" in cols and len(cols) >= 3) or ("name" in cols and "result" in cols)
    return cols if ok else None


def _is_totals_line(line: Line):
    for p in line_pairs(line):
        if p.id in TOTAL_IDS and p.value_words and all(
                is_numeric_token(w.text) or CUR_TOKEN_RE.fullmatch(w.text.strip(".:")) or w.text in {"(", ")"}
                for w in p.value_words):
            return True
    return False


def _bounds(cols, data_lines):
    items = sorted(((cid, min(w.x0 for w in ws), max(w.x1 for w in ws)) for cid, ws in cols.items()),
                   key=lambda t: (t[1] + t[2]) / 2)
    covered = [(w.x0, w.x1) for ln in data_lines for w in ln.words]
    out, left = [], 0.0
    for i, (cid, x0, x1) in enumerate(items):
        if i == len(items) - 1:
            right = 1.0
        else:
            lo, hi = x1, items[i + 1][1]
            if lo >= hi:                       # headers touch/overlap -> midpoint
                right = (lo + hi) / 2
            else:
                gaps, cur = [], lo
                for a, b in sorted(covered):
                    if b <= lo or a >= hi:
                        continue
                    if a > cur:
                        gaps.append((cur, a))
                    cur = max(cur, b)
                if cur < hi:
                    gaps.append((cur, hi))
                right = max(gaps, key=lambda g: g[1] - g[0]) if gaps else None
                right = (right[0] + right[1]) / 2 if right else (lo + hi) / 2
        out.append((cid, left, right))
        left = right
    return out


def _assign(line: Line, bounds):
    cells: Dict[str, List[Word]] = {}
    for w in line.words:
        for cid, l, r in bounds:
            if l <= w.cx < r or (r == 1.0 and w.cx >= l):
                cells.setdefault(cid, []).append(w)
                break
    return cells


def _text(ws):
    rtl = ar_ratio(" ".join(w.text for w in ws)) > 0.5
    return " ".join(w.text for w in logical_order(sorted(ws, key=lambda w: w.x0), rtl)).strip()


def _looks_section(line: Line):
    txt = " ".join(w.text for w in line.words)
    keys = {w.key for w in line.words}
    if keys & SECTION_WORDS:
        return True
    letters = re.sub(r"[^A-Za-z]", "", txt)
    return len(letters) >= 3 and letters.isupper() and len(line.words) <= 4


def _candidate_lines(page: Page, start: int):
    out, prev, hs = [], None, [l.height for l in page.lines] or [0.01]
    med = sorted(hs)[len(hs) // 2]
    for ln in page.lines[start:]:
        if prev is not None and ln.y - prev.y > med * 5 and out:
            break
        if header_columns(ln) and out:
            break
        if _is_totals_line(ln):
            break
        if {w.key for w in ln.words} & _STOP_WORDS:
            break
        if not _PAGE_OF.search(" ".join(w.text for w in ln.words)):
            out.append(ln)
        prev = ln
    return out


def parse_table(page: Page, header_idx: Optional[int], cols=None, kind=None, bounds=None, inherited=False, rtl=None) -> Optional[Table]:
    start = 0 if header_idx is None else header_idx + 1
    data = _candidate_lines(page, start)
    if not data:
        return None
    if bounds is None:
        bounds = _bounds(cols, data)
    if rtl is None:
        hw = [w for ws in cols.values() for w in ws]
        rtl = sum(has_ar(w.text) for w in hw) > len(hw) / 2
    t = Table(kind or _kind(set(cols)), page.number, header_idx, bounds, inherited=inherited, rtl=rtl)
    if header_idx is not None:
        t.line_idxs.add(page.lines[header_idx].idx)
    prev_row, prev_line = None, None
    hs = sorted(l.height for l in page.lines)
    med = hs[len(hs) // 2]
    for ln in data:
        cells = _assign(ln, bounds)
        for ws_ in cells.values():
            for w_ in ws_:
                w_.rtl_hint = t.rtl
        name = _text(cells.get("name", []))
        others = {c: ws for c, ws in cells.items() if c not in ("name", "no") and ws}
        numeric_ok = any(c in NUMERIC_COLS for c in others) if t.kind != "lab" else bool(cells.get("result"))
        if t.kind == "med":
            numeric_ok = bool(others)
        if name and numeric_ok:
            row = Row([ln.idx], cells, getattr(t, "_section", None), getattr(t, "_section_words", []), inherited)
            t.rows.append(row)
            t.line_idxs.add(ln.idx)
            prev_row, prev_line = row, ln
            continue
        if name and not others:
            near = prev_line is not None and (ln.y - prev_line.y) < med * 1.9
            if prev_row is not None and near and not _looks_section(ln):
                prev_row.cells["name"] = sorted(prev_row.cells.get("name", []) + cells["name"], key=lambda w: (round(w.cy, 3), w.x0))
                prev_row.line_idxs.append(ln.idx)
                t.line_idxs.add(ln.idx)
                prev_line = ln
            elif _looks_section(ln) or prev_row is None or not near:
                t._section = name
                t._section_words = cells["name"]
                t.line_idxs.add(ln.idx)
                prev_row, prev_line = None, ln
            continue
        if not name and others and prev_row is not None and (ln.y - prev_line.y) < med * 1.9:
            # numbers on a wrapped line belong to the previous row only if its cells are empty there
            for c, ws in others.items():
                if not prev_row.cells.get(c):
                    prev_row.cells[c] = ws
            prev_row.line_idxs.append(ln.idx)
            t.line_idxs.add(ln.idx)
            prev_line = ln
    return t if t.rows else None


def find_tables(page: Page, inherit: Optional[Table] = None) -> List[Table]:
    tables, consumed = [], set()
    for ln in page.lines:
        if ln.idx in consumed:
            continue
        cols = header_columns(ln)
        if not cols:
            continue
        t = parse_table(page, page.lines.index(ln), cols)
        if t:
            tables.append(t)
            consumed |= t.line_idxs
    if not tables and inherit is not None and inherit.kind == "invoice":
        t = parse_table(page, None, kind=inherit.kind, bounds=inherit.bounds, inherited=True, rtl=inherit.rtl)
        if t:
            tables.append(t)
    return tables


# Fallback is intentionally limited to scanned Arabic invoice pages with no detected table header.
# The layout is uncertain; results MUST be queued for human verification.
def unheaded_arabic_invoice_rows(page: Page) -> Optional[Table]:
    if page.method != "ocr":
        return None
    from .textutil import parse_number
    rows = []
    for ln in page.lines:
        if line_pairs(ln) or header_columns(ln):
            continue
        numbers = sorted([w for w in ln.words if w.conf >= .65 and parse_number(w.text) is not None
                          and re.fullmatch(r"[\d.,٠-٩٫٬]+", w.text)], key=lambda w: w.cx, reverse=True)
        if len(numbers) != 3:
            continue
        # Arabic data rows normally print the description to the right of qty, then unit price and total.
        qty, unit_price, line_total = numbers
        if not (qty.cx > unit_price.cx > line_total.cx):
            continue
        if parse_number(qty.text) <= 0 or parse_number(unit_price.text) < 0 or parse_number(line_total.text) < 0:
            continue
        desc = [w for w in ln.words if w.cx > qty.cx and w.conf >= .65 and has_ar(w.text)
                and len(match_key(w.text)) >= 2]
        if not desc:
            continue
        cells = {"name": desc, "qty": [qty], "unit_price": [unit_price], "total": [line_total]}
        rows.append(Row([ln.idx], cells, inherited=True))
    if not rows:
        return None
    t = Table("invoice", page.number, None, [], rows=rows, rtl=True, inherited=True)
    t.line_idxs = {i for r in rows for i in r.line_idxs}
    return t
