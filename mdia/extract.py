"""Evidence-first extraction of a logical document.

Every value is copied from words that physically exist on a page and is bound to an Evidence
record (page, text, bbox, method, confidence). Nothing is inferred from other values: a field
that is not printed stays empty with status 'not_found'."""
import re
from typing import Dict, List, Optional

from . import config
from .kv import KV, line_pairs, page_pairs
from .total_candidates import is_isolated_total
from .lexicon import INJECTION_PATTERNS
from .model import Page, Word, join_words, logical_order, union_bbox
from .tables import Table, find_tables, header_columns, unheaded_arabic_invoice_rows
from .textutil import (CUR_TOKEN_RE, ar_ratio, detect_currency, has_ar, last_amount, match_key, parse_date,
                       parse_number, ocr_arabic_comma_decimal, normalize_arabic_ocr_script, uncertain_arabic_ocr_letters,
                       has_ambiguous_final_farsi_yeh)

ICD_RE = re.compile(r"\b([A-TV-Z][0-9]{2}(?:\.[0-9A-Z]{1,4})?)\b")
STRENGTH_RE = re.compile(r"(?i)(\d+(?:[.,]\d+)?)\s*(mg|mcg|µg|g|ml|iu|units?|%|mmol|ملغ|ملجم|مجم|مل|ميكروغرام|وحده)(?!\s*/\s*dl)\b(?:\s*/\s*(\d+(?:[.,]\d+)?)?\s*(ml|mg|g|مل))?")
FORM_RE = re.compile(r"(?i)\b(tablets?|tabs?|capsules?|caps?|syrup|suspension|injection|inj|cream|ointment|drops|gel|lotion|suppository|inhaler|spray|sachet|patch|vial|ampoule|amp)\b|قرص|أقراص|اقراص|كبسولة|كبسولات|شراب|حقن|حقنة|مرهم|كريم|قطرة|قطرات|تحميلة|بخاخ")
FREQ_RE = re.compile(r"(?i)\b(qd|od|bid|bd|tid|tds|qid|qds|prn|stat|qhs|hs|q\d+h|every\s+\d+\s+hours?|(?:once|twice|\d+\s*times?)\s+(?:a\s+|per\s+)?(?:daily|day)|\d\s*[x×]\s*\d)\b|مرة يوميا|مرتين يوميا|ثلاث مرات يوميا|مرة واحدة يوميا|كل \d+ ساعات?|\d+ مرات? يوميا")
DUR_RE = re.compile(r"(?i)(?:for\s+)?(\d+)\s*(days?|weeks?|months?)|لمدة\s*(\d+)\s*(يوم|ايام|أيام|اسبوع|أسابيع|اسابيع|شهر|اشهر|أشهر)")
ROUTE_RE = re.compile(r"(?i)\b(oral|po|iv|im|sc|sl|topical|rectal|inhaled|ophthalmic|otic|nasal)\b|فموي|وريدي|عضلي|موضعي")
SUSPECT_RE = re.compile(r"(?i)suspect|probable|possible|provisional|rule out|\br/o\b|\?|query|differential|مشتبه|محتمل|اشتباه|مبدئي|ربما|للاستبعاد")
CONFIRM_RE = re.compile(r"(?i)confirmed|definite|established|مؤكد|مثبت")
NOT_FOUND = {"raw": None, "value": None, "evidence_id": None, "page": None, "confidence": 0.0,
             "status": "not_found", "verification": "not_applicable"}
FAC_RE = re.compile(r"(?i)hospital|clinic|medical cent|pharmacy|laborator|polyclinic|مستشفى|عياده|عيادة|مركز|صيدليه|صيدلية|مختبر|مجمع")
NOT_FAC_RE = re.compile(r"(?i)invoice|bill|report|receipt|statement|prescription|فاتوره|فاتورة|تقرير|وصفه|وصفة|كشف|ايصال|إيصال")
BULLET_RE = re.compile(r"^\s*(?:[-•*·▪●]|\d{1,2}[.)])\s*")


def _nf():
    return dict(NOT_FOUND)


_CONFUSE = {"O": "0", "o": "0", "l": "1", "I": "1", "|": "1", "S": "5", "B": "8", "Z": "2"}


def ocr_digit_suggestion(raw: str):
    """Suggest (never apply) a reading for a numeric OCR token damaged by look-alike characters,
    e.g. '45:25' -> 45.25, 'l,200.OO' -> 1,200.00. Returns Decimal or None."""
    allowed = set("0123456789.,:;()-+") | set(_CONFUSE)
    if not raw or any(c not in allowed for c in raw) or sum(c.isdigit() for c in raw) < 1:
        return None                                    # only tokens that already look numeric are candidates
    t = re.sub(r"(?<=\d)[:;](?=\d)", ".", raw)
    t = "".join(_CONFUSE.get(c, c) for c in t)
    return parse_number(t) if t != raw else None


class Ctx:
    """Per-document state: evidence store + field factory."""

    def __init__(self, job_id: str, doc_id: str, pages: Dict[int, Page]):
        self.job_id, self.doc_id, self.pages = job_id, doc_id, pages
        self.evidence: List[dict] = []
        self._ev_index = {}
        self.warnings: List[dict] = []
        self.counters: Dict[str, int] = {}

    def rid(self, prefix):
        self.counters[prefix] = self.counters.get(prefix, 0) + 1
        return f"{self.doc_id}-{prefix}{self.counters[prefix]}"

    def warn(self, kind, message, severity="warning", **extra):
        self.warnings.append({"id": f"{self.doc_id}-w{len(self.warnings) + 1}", "kind": kind, "severity": severity,
                              "message": message, **extra})

    def evidence_for(self, page: Page, words: List[Word], raw: str, source: str, boxes=None, mult=1.0) -> Optional[str]:
        if not words:
            return None
        bbox = union_bbox(words)
        key = (page.number, tuple(bbox), raw)
        if key in self._ev_index:
            return self._ev_index[key]
        conf = sum(w.conf for w in words) / len(words)
        conf = conf * (0.97 if page.method == "text-layer" else 0.95)
        eid = f"{self.doc_id}-ev{len(self.evidence) + 1}"
        if page.flags.get("ocr_engine") == "paddleocr-v5-arabic":
            # Some fields pass the whole source line. Never tag these as
            # precisely word-localized even if the second OCR matched tokens.
            selected = join_words(sorted(words, key=lambda w: w.x0),
                                  ar_ratio(" ".join(w.text for w in words)) > 0.5)
            exact_scope = match_key(selected) == match_key(raw)
            geometry_source = ("cross_engine_word_match"
                               if exact_scope and all(w.geometry_source == "cross_engine_word_match" for w in words)
                               else "line_interpolated")
        else:
            geometry_source = "pdf_text" if page.method == "text-layer" else "tesseract_word"
        self.evidence.append({
            "geometry_source": geometry_source, "word_box_verified": False,
            "id": eid, "document_id": self.doc_id, "page": page.number, "text": source, "matched_text": raw,
            "bbox": bbox, "bboxes": boxes or [bbox], "method": page.method, "confidence": round(conf * mult, 3)})
        self._ev_index[key] = eid
        return eid

    def field(self, page: Page, words: List[Word], raw: Optional[str] = None, kind="text", source=None,
              mult=1.0, boxes=None, note=None) -> dict:
        words = [w for w in words if w is not None]
        if not words:
            return _nf()
        hints = [w.rtl_hint for w in words if w.rtl_hint is not None]
        rtl = hints[0] if hints else ar_ratio(" ".join(w.text for w in words)) > 0.5
        raw_text = (raw if raw is not None else join_words(sorted(words, key=lambda w: (round(w.cy, 2), w.x0)), rtl)).strip()
        if not raw_text:
            return _nf()
        value, status, reasons = raw_text, "extracted", []
        ev_words = words
        if kind == "money":
            tok, num = last_amount(raw_text, allow_ocr_arabic_comma=page.method == "ocr")
            if num is not None:
                raw_text = tok.strip(":؛;")
                value = float(num)
                ev_words = [w for w in words if w.text.strip(":؛;") == raw_text] or words
                if page.method == "ocr" and ocr_arabic_comma_decimal(raw_text) is not None:
                    # OCR may confuse the Arabic punctuation comma with an
                    # actual printed decimal separator. A candidate, NOT a
                    # verified monetary amount; retain evidence and review.
                    reasons.append("ocr_arabic_comma_decimal_candidate")
            else:
                value, status = None, "unreadable"
                reasons.append("unparseable_number")
        elif kind == "number":
            num = (ocr_arabic_comma_decimal(raw_text) if page.method == "ocr"
                   else None) if "،" in raw_text else parse_number(raw_text)
            if num is not None and "،" in raw_text:
                reasons.append("ocr_arabic_comma_decimal_candidate")
            if num is None:
                value, status = None, "unreadable"
                reasons.append("unparseable_number")
            else:
                value = float(num)
        elif kind == "date":
            iso, n = parse_date(raw_text)
            value = iso
            if iso is None:
                status = "unreadable" if n in ("no_date_found", "invalid_date") else "ambiguous"
                reasons.append(n)
        elif kind == "text" and page.method == "ocr":
            # Paddle Arabic recognition may emit Persian yeh/kaf codepoints.
            # A final/isolated Farsi yeh can be Arabic ي OR ى; never decide
            # from that glyph alone (e.g. kidney term كلى vs adjective كلي).
            # Always preserve source evidence and never rewrite financial data.
            normalized = normalize_arabic_ocr_script(raw_text)
            if normalized != raw_text:
                value = normalized
                reasons.append("arabic_ocr_script_variant")
            if has_ambiguous_final_farsi_yeh(raw_text):
                reasons.append("ambiguous_final_farsi_yeh")
            if uncertain_arabic_ocr_letters(raw_text):
                # An Urdu/Persian letter is NOT proof of its visually similar
                # Arabic counterpart. Keep it verbatim and require a reviewer.
                reasons.append("ocr_extended_arabic_letter")
        m = mult
        if page.flags.get("arabic_visual_order_fixed") and has_ar(raw_text):
            m *= 0.92
        if note:
            reasons.append(note)
        src = source or " ".join(w.text for w in words)
        eid = self.evidence_for(page, ev_words, raw_text, src, boxes, m)
        conf = next(e["confidence"] for e in self.evidence if e["id"] == eid)
        if status != "extracted":
            conf = round(conf * 0.5, 3)
        verification = "needs_review" if (conf < config.LOW_CONF or status != "extracted"
                                          or "arabic_ocr_script_variant" in reasons
                                          or "ambiguous_final_farsi_yeh" in reasons
                                          or "ocr_extended_arabic_letter" in reasons
                                          or "ocr_arabic_comma_decimal_candidate" in reasons) else "unverified"
        f = {"raw": raw_text, "value": value, "evidence_id": eid, "page": page.number, "confidence": conf,
             "status": status, "verification": verification}
        if reasons:
            f["review_reasons"] = reasons
        if status == "unreadable" and kind in ("money", "number") and page.method == "ocr":
            sug = ocr_digit_suggestion(raw_text)
            if sug is not None:
                f["suggestion"] = {"value": float(sug), "reason": "ocr_character_confusion", "applied": False}
        return f


# ------------------------------------------------------------------ helpers
def _first(pairs: List[KV], ids, nonempty=True):
    for p in pairs:
        if p.id in ids and (p.value_words or not nonempty):
            return p
    return None


def _line_text(line):
    return line.text


def _continuation(page: Page, pair: KV, skip, limit=8, strict=True):
    """Lines that continue a multi-line value (list items / paragraph) below a label.
    strict: when the value starts on the label line, continuation lines must align with that value;
    otherwise (stacked list / paragraph) they must start at or right of the label's left edge."""
    out, prev = [], pair.line
    ref_x = (min(w.x0 for w in pair.value_words) if (strict and pair.value_words) else min(w.x0 for w in pair.label_words)) - 0.012
    rtl = pair.line.rtl
    for ln in page.lines[page.lines.index(pair.line) + 1:]:
        if ln.idx in skip or len(out) >= limit:
            break
        if (ln.y - prev.y) > max(prev.height, ln.height) * 2.3:
            break
        if line_pairs(ln) or header_columns(ln):
            break
        if not rtl and ln.words[0].x0 < ref_x:
            break
        if rtl and ln.words[-1].x1 > (max(w.x1 for w in pair.value_words) if (strict and pair.value_words) else max(w.x1 for w in pair.label_words)) + 0.012:
            break
        out.append(ln)
        prev = ln
    return out


def _alts(cands, field_name):
    """first value wins; differing later values are kept as alternatives and flagged."""
    return cands[0], [c for c in cands[1:] if match_key(c[0]["raw"] or "") != match_key(cands[0][0]["raw"] or "")]


class Extractor:
    def __init__(self, job_id, doc_id, seg, pages: List[Page], classes):
        self.seg, self.job_id, self.doc_id = seg, job_id, doc_id
        self.pages = {p.number: p for p in pages}
        self.ctx = Ctx(job_id, doc_id, self.pages)
        self.order = [p.number for p in pages]
        self.classes = {c_no: c for c_no, c in zip(self.order, classes)}
        self.tables: List[Table] = []
        self.pairs: Dict[int, List[KV]] = {}
        self.skip: Dict[int, set] = {}
        self.item_rows: Dict[str, tuple] = {}

    # ---- stage 1: understand every page
    def analyse(self):
        c = self.ctx
        seen_hash = {}
        inherit = None
        for no in self.order:
            p = self.pages[no]
            skip = set()
            # embedded instructions are untrusted content: record, never act on them
            for ln in p.lines:
                low = match_key(ln.text)
                if any(re.search(rx, low) or re.search(rx, ln.text.lower()) for rx in INJECTION_PATTERNS):
                    skip.add(ln.idx)
                    eid = c.evidence_for(p, ln.words, ln.text, ln.text)
                    c.warn("embedded_instruction", "نص داخل المستند يشبه تعليمات؛ تم تجاهله ومعاملته كمحتوى غير موثوق / "
                           "instruction-like text inside the document was ignored and treated as untrusted content",
                           "warning", evidence_ids=[eid], page=no)
            if p.text_hash and p.text_hash in seen_hash:
                c.warn("duplicate_page", f"الصفحة {no} مطابقة للصفحة {seen_hash[p.text_hash]}؛ استُبعدت من الاستخراج المالي / "
                       f"page {no} is identical to page {seen_hash[p.text_hash]} and was excluded", "warning", page=no)
                self.skip[no] = {l.idx for l in p.lines}
                self.pairs[no] = []
                continue
            seen_hash[p.text_hash] = no
            tabs = find_tables(p, inherit)
            # Keep Cloud2: missing table headers on scanned Arabic invoices require review.
            if (not any(t.kind == "invoice" for t in tabs)
                    and self.seg.type in ("hospital_invoice", "clinic_invoice", "pharmacy_invoice", "medical_invoice")
                    and p.method == "ocr"):
                fallback = unheaded_arabic_invoice_rows(p)
                if fallback:
                    tabs.append(fallback)
                    c.warn("unheaded_invoice_table", "جدول الفاتورة بلا ترويسة موثقة؛ البنود المستخرجة تحتاج مراجعة بشرية / "
                           "invoice table has no verified header; extracted rows require human review", "warning", page=no)
            for t in tabs:
                self.tables.append(t)
                skip |= t.line_idxs
                if t.kind == "invoice" and not t.inherited:
                    inherit = t
                if t.inherited:
                    c.warn("table_layout_inherited", f"الصفحة {no} بلا ترويسة جدول؛ استُخدم تخطيط الصفحة السابقة (ثقة أقل) / "
                           f"no table header on page {no}: column layout inherited from the previous page", "info", page=no)
            self.skip[no] = skip
            self.pairs[no] = page_pairs(p, skip)
            for w in p.warnings:
                c.warn(w["kind"], w["message"], "warning", page=no)
            if p.flags.get("ocr_mean_conf") is not None and p.flags["ocr_mean_conf"] < 0.6:
                c.warn("low_ocr_quality", f"جودة OCR منخفضة في الصفحة {no} (متوسط الثقة {p.flags['ocr_mean_conf']}) / "
                       f"low OCR quality on page {no}", "warning", page=no)

    def all_pairs(self, ids):
        for no in self.order:
            for kv in self.pairs.get(no, []):
                if kv.id in ids:
                    yield no, kv

    # ---- stage 2: header-like fields (first value wins, conflicts flagged)
    def _single(self, ids, kind="text", label=None):
        cands = []
        for no, kv in self.all_pairs(ids):
            if not kv.value_words:
                continue
            p = self.pages[no]
            mult = 0.85 if kv.layout == "below" else 1.0
            f = self.ctx.field(p, kv.value_words, kind=kind, source=_line_text(kv.line), mult=mult,
                               note="value_below_label" if kv.layout == "below" else None)
            if f["status"] != "not_found":
                cands.append((f, kv))
        if not cands:
            return _nf()
        best = next((c for c in cands if c[0]["status"] == "extracted"), cands[0])
        f = dict(best[0])
        alts = [c[0] for c in cands if c[0] is not best[0] and match_key(c[0]["raw"] or "") != match_key(f["raw"] or "")]
        if alts:
            f["alternatives"] = [{"raw": a["raw"], "evidence_id": a["evidence_id"], "page": a["page"]} for a in alts]
            f["verification"] = "needs_review"
            f.setdefault("review_reasons", []).append("conflicting_values")
            self.ctx.warn("conflicting_values", f"قيم متعارضة لـ {label or ids}: {[f['raw']] + [a['raw'] for a in alts]} / "
                          f"conflicting values found", "warning", evidence_ids=[f["evidence_id"]] + [a["evidence_id"] for a in alts])
        return f

    def patient(self):
        return {
            "name": self._single({"patient.name"}, label="patient.name"),
            "file_no": self._single({"patient.file_no"}, label="patient.file_no"),
            "insurance_no": self._single({"patient.insurance_no"}, label="patient.insurance_no"),
            "age": self._single({"patient.age"}),
            "sex": self._single({"patient.sex"}),
            "date_of_birth": self._single({"patient.dob"}, kind="date"),
        }

    def provider(self):
        fac = self._single({"provider.facility"}, label="provider.facility")
        if fac["status"] == "not_found":
            p = self.pages[self.order[0]]
            for ln in p.lines[:6]:
                txt = ln.text
                if FAC_RE.search(txt) and not NOT_FAC_RE.search(txt) and not any(k.value_words for k in line_pairs(ln)):
                    fac = self.ctx.field(p, ln.words, source=txt, mult=0.85, note="facility_from_page_header")
                    break
        return {"facility_name": fac, "doctor": self._single({"provider.doctor"}, label="provider.doctor"),
                "department": self._single({"provider.department"})}

    # ---- stage 3: financial
    def _currency(self):
        for no, kv in self.all_pairs({"invoice.currency"}):
            raw, iso = detect_currency(kv.value_text) if kv.value_words else (None, None)
            if kv.value_words:
                f = self.ctx.field(self.pages[no], kv.value_words, source=kv.line.text)
                if iso:
                    f["value"] = iso
                else:
                    f["value"] = None
                    f["verification"] = "needs_review"
                    f.setdefault("review_reasons", []).append("ambiguous_currency")
                return f
        for no in self.order:
            p = self.pages[no]
            for ln in p.lines:
                if ln.idx in self.skip.get(no, set()) and not self._in_total_row(no, ln):
                    pass
                for w in ln.words:
                    raw, iso = detect_currency(w.text)
                    if raw and w.conf >= 0.6 and re.search(r"\d", ln.text):
                        f = self.ctx.field(p, [w], source=ln.text, mult=0.9)
                        if iso:
                            f["value"] = iso
                        else:
                            f["value"] = None
                            f["verification"] = "needs_review"
                            f.setdefault("review_reasons", []).append("ambiguous_currency")
                        return f
        return _nf()

    def _in_total_row(self, no, ln):
        return False

    def invoice(self, items_present):
        t = self.seg.type
        invoice_like = t.endswith("_invoice") or t in ("payment_receipt", "account_statement", "services_statement")
        fields = {
            "invoice_number": self._single({"invoice.number"}, label="invoice.number"),
            "invoice_date": self._single({"invoice.date"}, kind="date", label="invoice.date"),
            "service_date": self._single({"invoice.service_date"}, kind="date"),
            "currency": self._currency(),
        }
        totals = {}
        for key, fid in [("subtotal", "fin.subtotal"), ("discount_total", "fin.discount"), ("tax_total", "fin.tax"),
                         ("additional_fees", "fin.fees"), ("invoice_total", "fin.total"), ("paid_total", "fin.paid"),
                         ("balance_due", "fin.balance"), ("patient_share", "fin.patient_share"), ("claimed_total", "fin.claimed")]:
            cands = []
            for no, kv in self.all_pairs({fid}):
                if (kv.value_words and last_amount(kv.value_text, allow_ocr_arabic_comma=self.pages[no].method == "ocr")[1] is not None
                        and (key != "invoice_total" or is_isolated_total(kv))):
                    cands.append(self.ctx.field(self.pages[no], kv.value_words, kind="money", source=_line_text(kv.line)))
            if not cands:
                totals[key] = _nf()
                continue
            f = dict(cands[-1])                       # grand totals sit at the end of the document
            distinct = {c["value"] for c in cands}
            if len(distinct) > 1:
                f["alternatives"] = [{"raw": c["raw"], "evidence_id": c["evidence_id"], "page": c["page"]} for c in cands[:-1]]
                f["verification"] = "needs_review"
                f.setdefault("review_reasons", []).append("multiple_candidates")
                self.ctx.warn("multiple_total_candidates", f"عدة قيم لـ {key}: {[c['raw'] for c in cands]}؛ اختير آخرها / "
                              f"several candidates for {key}; the last one was used", "warning",
                              evidence_ids=[c["evidence_id"] for c in cands])
            totals[key] = f
        fields.update(totals)
        has_data = any(v["status"] != "not_found" for v in fields.values())
        if not (invoice_like or items_present or has_data and fields["invoice_total"]["status"] != "not_found"):
            return []
        if not has_data and not items_present:
            return []
        rec = {"id": self.ctx.rid("inv"), "kind": t if invoice_like else "invoice_like", "pages": self.order, **fields}
        return [rec]

    def _row_text(self, p: Page, row):
        lines = [l for l in p.lines if l.idx in row.line_idxs]
        return " ⏎ ".join(l.text for l in lines)

    def invoice_items(self, inv_id, section_pharmacy: List[dict], meds_from_items: List[tuple]):
        items = []
        for t in self.tables:
            if t.kind != "invoice":
                continue
            p = self.pages[t.page]
            for row in t.rows:
                src = self._row_text(p, row)
                mult = 0.85 if row.inherited else 1.0
                F = lambda col, kind="text", **kw: self.ctx.field(p, row.cells.get(col, []), kind=kind, source=src, mult=mult, **kw)
                name_ws = sorted(row.cells.get("name", []), key=lambda w: (round(w.cy, 3), w.x0))
                first_idx = next((l.idx for l in p.lines if any(w in l.words for w in name_ws)), None)
                first_ws = [w for w in name_ws if first_idx is not None and any(w is x for x in p.lines[first_idx].words)] if first_idx is not None else name_ws
                rest_ws = [w for w in name_ws if not any(w is x for x in first_ws)]
                it = {
                    "id": self.ctx.rid("it"), "invoice_id": inv_id, "page": p.number,
                    "line_no": F("no", "number"),
                    "service_name": self.ctx.field(p, first_ws, source=src, mult=mult),
                    "description": self.ctx.field(p, rest_ws, source=src, mult=mult) if rest_ws else _nf(),
                    "service_type": F("type") if row.cells.get("type") else (
                        self.ctx.field(p, row.section_words, source=row.section or "", mult=mult, note="from_section_header") if row.section_words else _nf()),
                    "service_code": F("code"),
                    "service_date": F("date", "date"),
                    "quantity": F("qty", "number"), "unit": F("unit"),
                    "unit_price": F("unit_price", "money"), "discount": F("discount", "money"),
                    "line_total": F("total", "money"), "claimed_amount": F("claimed", "money"),
                    "paid_amount": F("paid", "money"), "patient_share": F("patient_share", "money"),
                    "section": row.section,
                }
                items.append(it)
                self.item_rows[it["id"]] = (it, p, row, src)
                sec = match_key(row.section or "")
                if sec and (sec in {"pharmacy", "medications", "medicines", "صيدليه", "ادويه"}):
                    meds_from_items.append((it, p, row, src))
        return items

    # ---- stage 4: clinical
    def medications(self, items_meds, pharmacy_doc_items):
        meds = []
        # (a) medication tables
        for t in self.tables:
            if t.kind != "med":
                continue
            p = self.pages[t.page]
            for row in t.rows:
                src = self._row_text(p, row)
                F = lambda col, kind="text": self.ctx.field(p, row.cells.get(col, []), kind=kind, source=src)
                name_f = F("name")
                strength = F("strength")
                if strength["status"] == "not_found":
                    m = STRENGTH_RE.search(name_f["raw"] or "")
                    if m:
                        sw = [w for w in row.cells.get("name", []) if m.group(1) in w.text or m.group(2).lower() in w.text.lower()] or row.cells["name"]
                        strength = self.ctx.field(p, sw, raw=m.group(0), source=src, mult=0.9, note="strength_from_name_text")
                meds.append(self._med_record(p, name_f, strength, F, source="medication_table"))
        # (b) medications billed as invoice items (explicit pharmacy section, or pharmacy invoice)
        for it, p, row, src in items_meds:
            m = STRENGTH_RE.search(it["service_name"]["raw"] or "")
            strength = _nf()
            if m:
                strength = self.ctx.field(p, row.cells["name"], raw=m.group(0), source=src, mult=0.9, note="strength_from_name_text")
            rec = self._med_record(p, it["service_name"], strength, lambda c, k="text": _nf(), source="invoice_item")
            rec["quantity_dispensed"] = it["quantity"]
            rec["unit_price"] = it["unit_price"]
            rec["total_price"] = it["line_total"]
            rec["invoice_item_id"] = it["id"]
            meds.append(rec)
        # (c) free text prescription lines
        if self.seg.type in ("prescription", "medical_report", "discharge_summary"):
            tl = set()
            for t in self.tables:
                tl |= t.line_idxs
            for no in self.order:
                p = self.pages[no]
                for ln in p.lines:
                    if ln.idx in self.skip.get(no, set()) or ln.idx in tl or line_pairs(ln):
                        continue
                    txt = BULLET_RE.sub("", ln.text).strip()
                    # Explicit Rx lines are medicines even when their concentration is not printed.
                    explicit_rx = re.match(r"(?i)^(?:rx|medication|medicine|drug)\s*[:\-]\s*", txt)
                    if explicit_rx:
                        txt = txt[explicit_rx.end():].strip()
                    m = STRENGTH_RE.search(txt)
                    if not m and not explicit_rx:
                        continue
                    if m and m.start() == 0:
                        continue
                    name_part = txt[:m.start()] if m else txt
                    # Remove directions that are not part of the drug name, without guessing.
                    if not m:
                        directions = re.search(r"(?i)\b(?:prn|once|twice|daily|oral|bid|tid|for \d+ days?)\b", name_part)
                        if directions:
                            name_part = name_part[:directions.start()]
                    name = name_part.strip(" -:,;.")
                    list_number_removed = False
                    if p.method == "ocr" and not explicit_rx:
                        # OCR may read an Arabic list marker as ١٠ or ٢٠.
                        # Remove only a digit-only prefix before an Arabic name;
                        # do not guess its ordinal or a dosage.
                        marker = re.fullmatch(r"[0-9٠-٩]{1,2}[.)]?\s+(.+)", name)
                        if marker and has_ar(marker.group(1)):
                            name = marker.group(1).strip()
                            list_number_removed = True
                    if not name or len(name) > 80:
                        continue
                    if not explicit_rx and not (FORM_RE.search(txt) or FREQ_RE.search(txt)):
                        continue
                    ws = ln.words
                    name_f = self.ctx.field(p, ws, raw=name, source=ln.text,
                                            mult=0.64 if list_number_removed else 0.8,
                                            note="ocr_list_prefix_removed_needs_review" if list_number_removed else "free_text_line")
                    str_f = (self.ctx.field(p, ws, raw=m.group(0), source=ln.text, mult=0.8)
                             if m else _nf())

                    def rx(rx_, grp=0):
                        mm = rx_.search(txt)
                        return self.ctx.field(p, ws, raw=mm.group(grp), source=ln.text, mult=0.8) if mm else _nf()
                    rec = self._med_record(p, name_f, str_f, lambda c, k="text": _nf(), source="free_text")
                    rec["dosage_form"] = rx(FORM_RE)
                    rec["frequency"] = rx(FREQ_RE)
                    rec["duration"] = rx(DUR_RE)
                    rec["route"] = rx(ROUTE_RE)
                    meds.append(rec)
        return meds

    def _med_record(self, p, name_f, strength, F, source):
        return {"id": self.ctx.rid("med"), "page": p.number, "source": source,
                "brand_name": name_f, "generic_name": F("generic"), "strength": strength,
                "dosage_form": F("form"), "dose": F("dose"), "route": F("route"), "frequency": F("frequency"),
                "duration": F("duration"), "quantity_prescribed": F("prescribed", "number") if F("prescribed")["status"] != "not_found" else F("qty", "number"),
                "quantity_dispensed": F("dispensed", "number"), "packs": F("packs", "number"),
                "unit_price": F("unit_price", "money"), "total_price": F("total", "money"),
                "prescription_date": self._single({"invoice.date"}, kind="date") if source == "medication_table" and self.seg.type == "prescription" else _nf(),
                "prescriber": self._single({"provider.doctor"}) if self.seg.type == "prescription" else _nf(),
                "invoice_item_id": None}

    def diagnoses(self):
        out = []
        cat = {"dx.principal": "primary", "dx.secondary": "secondary", "dx.provisional": "provisional",
               "dx.final": "final", "dx.generic": "unspecified"}
        doctor = self._single({"provider.doctor"})
        for no, kv in self.all_pairs(set(cat) | {"clin.symptoms", "clin.chronic"}):
            p = self.pages[no]
            lines = ([(kv.line, sorted(kv.value_words, key=lambda w: w.x0))] if kv.value_words else []) + \
                    [(l, l.words) for l in _continuation(p, kv, self.skip.get(no, set()))
                     if not (STRENGTH_RE.search(l.text) and FORM_RE.search(l.text))
                     and not (kv.layout == "below" and l.idx == kv.line.idx + 1)]
            for ln, ws in lines:
                txt = BULLET_RE.sub("", join_words(ws))
                parts = [s for s in re.split(r"[;؛]|،", txt) if s.strip()]
                for part in parts:
                    part = part.strip()
                    pws = [w for w in ws if w.text.strip(",;،؛") and w.text.strip(",;،؛") in part.split()] or ws
                    f = self.ctx.field(p, pws, raw=part, source=ln.text)
                    if f["status"] == "not_found":
                        continue
                    if kv.id in ("clin.symptoms", "clin.chronic"):
                        out.append({"id": self.ctx.rid("dx"), "page": no, "entry_type": "symptom" if kv.id == "clin.symptoms" else "chronic_condition",
                                    "text": f, "category": "not_applicable", "icd10": _nf(), "certainty": "not_applicable",
                                    "diagnosis_date": _nf(), "doctor": _nf(), "source_document_id": self.doc_id})
                        continue
                    icd = _nf()
                    mi = None
                    for mm in ICD_RE.finditer(part):
                        ctx_before = part[max(0, mm.start() - 8):mm.start()].lower()
                        if "." in mm.group(1) or re.search(r"[(\[]\s*$", part[:mm.start()]) or "icd" in ctx_before:
                            mi = mm
                            break
                    if mi:
                        icd = self.ctx.field(p, pws, raw=mi.group(1), source=ln.text)
                    certainty = "suspected" if (kv.id == "dx.provisional" or SUSPECT_RE.search(part)) else \
                        "confirmed" if (kv.id == "dx.final" or CONFIRM_RE.search(part)) else "not_stated"
                    out.append({"id": self.ctx.rid("dx"), "page": no, "entry_type": "diagnosis", "text": f,
                                "category": cat[kv.id], "icd10": icd, "certainty": certainty,
                                "diagnosis_date": _nf(), "doctor": doctor if doctor.get("page") == no else _nf(),
                                "source_document_id": self.doc_id})
        return out

    def labs(self):
        out = []
        page_date = {}
        for no, kv in self.all_pairs({"invoice.date", "img.date"}):
            if kv.value_words and no not in page_date:
                page_date[no] = (self.ctx.field(self.pages[no], kv.value_words, kind="date", source=kv.line.text, note="date_from_page_header"))
        for t in self.tables:
            if t.kind != "lab":
                continue
            p = self.pages[t.page]
            for row in t.rows:
                src = self._row_text(p, row)
                F = lambda col, kind="text": self.ctx.field(p, row.cells.get(col, []), kind=kind, source=src)
                d = F("date", "date")
                if d["status"] == "not_found" and t.page in page_date:
                    d = page_date[t.page]
                out.append({"id": self.ctx.rid("lab"), "page": p.number, "category": row.section,
                            "test_name": F("name"), "result": F("result"), "unit": F("unit"),
                            "reference_range": F("ref_range"), "flag": F("flag"), "test_date": d,
                            "price": F("total", "money") if row.cells.get("total") else F("unit_price", "money")})
        return out

    def imaging(self):
        out = []
        if self.seg.type != "radiology_report" and not any(True for _ in self.all_pairs({"img.exam", "img.region"})):
            return out
        by_page = {}
        for no, kv in self.all_pairs({"img.exam", "img.region", "img.findings", "img.date"}):
            by_page.setdefault(no, []).append(kv)
        for no, kvs in by_page.items():
            p = self.pages[no]
            rec = {"id": self.ctx.rid("img"), "page": no, "exam_type": _nf(), "region": _nf(), "findings": _nf(),
                   "exam_date": _nf(), "cost": _nf()}
            for kv in kvs:
                key = {"img.exam": "exam_type", "img.region": "region", "img.findings": "findings", "img.date": "exam_date"}[kv.id]
                if rec[key]["status"] != "not_found":
                    continue
                if key == "findings":
                    cont = _continuation(p, kv, self.skip.get(no, set()), strict=False)
                    vws = sorted(kv.value_words, key=lambda w: w.x0)
                    ws = vws + [w for l in cont for w in l.words]
                    texts = ([join_words(vws)] if vws else []) + [l.text for l in cont]
                    raw = " ".join(t for t in texts if t).strip()
                    boxes = [union_bbox(vws)] if vws else []
                    boxes += [l.bbox for l in cont]
                    rec[key] = self.ctx.field(p, ws, raw=raw, source=kv.line.text, boxes=[b for b in boxes if b])
                else:
                    rec[key] = self.ctx.field(p, kv.value_words, kind="date" if key == "exam_date" else "text", source=kv.line.text)
            if rec["exam_date"]["status"] == "not_found":
                for _, kv in self.all_pairs({"invoice.date"}):
                    if kv.value_words and kv.line in p.lines:
                        rec["exam_date"] = self.ctx.field(p, kv.value_words, kind="date", source=kv.line.text, note="date_from_page_header")
                        break
            if any(rec[k]["status"] != "not_found" for k in ("exam_type", "region", "findings")):
                out.append(rec)
        return out

    def procedures(self):
        ids = {"proc.name", "proc.surgeon", "proc.date", "proc.code", "proc.surgeon_fee", "proc.anesthesia_fee",
               "proc.or_fee", "proc.supplies", "proc.total"}
        by_page = {}
        for no, kv in self.all_pairs(ids):
            by_page.setdefault(no, []).append(kv)
        out = []
        for no, kvs in by_page.items():
            p = self.pages[no]
            if not any(k.id == "proc.name" and k.value_words for k in kvs):
                continue
            rec = {"id": self.ctx.rid("proc"), "page": no, "procedure_name": _nf(), "procedure_type": _nf(), "code": _nf(),
                   "date": _nf(), "surgeon": _nf(), "surgeon_fee": _nf(), "anesthesia_fee": _nf(), "or_fee": _nf(),
                   "supplies_cost": _nf(), "total_cost": _nf()}
            mapping = {"proc.name": ("procedure_name", "text"), "proc.surgeon": ("surgeon", "text"), "proc.date": ("date", "date"),
                       "proc.code": ("code", "text"), "proc.surgeon_fee": ("surgeon_fee", "money"),
                       "proc.anesthesia_fee": ("anesthesia_fee", "money"), "proc.or_fee": ("or_fee", "money"),
                       "proc.supplies": ("supplies_cost", "money"), "proc.total": ("total_cost", "money")}
            for kv in kvs:
                key, kind = mapping[kv.id]
                if rec[key]["status"] == "not_found" and kv.value_words:
                    rec[key] = self.ctx.field(p, kv.value_words, kind=kind, source=kv.line.text)
            out.append(rec)
        return out

    def stay_cost_from_items(self, h, items):
        """Room charge explicitly billed as a line whose name IS a stay-cost label (e.g. "Room Charges")."""
        from .lexicon import LABELS
        labels = {match_key(x) for x in LABELS["stay.cost"]}
        if h.get("accommodation_cost", {}).get("status") != "not_found":
            return
        for it in items:
            if match_key(it["service_name"]["raw"] or "") in labels and it["line_total"]["status"] == "extracted":
                f = dict(it["line_total"])
                f["confidence"] = round(f["confidence"] * 0.9, 3)
                f["derived_from_item"] = it["id"]
                h["accommodation_cost"] = f
                return

    def hospitalization(self):
        spec = {"admission_date": ({"stay.admit"}, "date"), "discharge_date": ({"stay.discharge"}, "date"),
                "length_of_stay_days": ({"stay.days"}, "number"), "room_type": ({"stay.room"}, "text"),
                "accommodation_cost": ({"stay.cost"}, "money")}
        h = {k: self._single(ids, kind=kd) for k, (ids, kd) in spec.items()}
        return h if any(v["status"] != "not_found" for v in h.values()) else {}


def extract_document(job_id, doc_id, seg, pages, classes) -> dict:
    ex = Extractor(job_id, doc_id, seg, pages, classes)
    ex.analyse()
    invoices = ex.invoice(items_present=any(t.kind == "invoice" for t in ex.tables))
    inv_id = invoices[0]["id"] if invoices else None
    items_meds: List[tuple] = []
    items = ex.invoice_items(inv_id, [], items_meds) if (invoices or any(t.kind == "invoice" for t in ex.tables)) else []
    if seg.type == "pharmacy_invoice":
        items_meds = [ex.item_rows[i["id"]] for i in items if i["id"] in ex.item_rows]
    meds = ex.medications(items_meds, None)
    doc = {
        "document_id": doc_id, "document_type": seg.type, "document_type_confidence": seg.confidence,
        "processing_status": "completed", "pages": seg.pages,
        "patient": ex.patient(), "provider": ex.provider(),
        "invoices": invoices, "invoice_items": items, "medications": meds,
        "diagnoses": ex.diagnoses(), "laboratory_tests": ex.labs(), "imaging": ex.imaging(),
        "procedures": ex.procedures(), "hospitalization": ex.hospitalization(),
        "evidence": ex.ctx.evidence, "warnings": ex.ctx.warnings, "requires_human_review": [],
        "notes": seg.notes,
    }
    if doc["hospitalization"]:
        ex.stay_cost_from_items(doc["hospitalization"], items)
    return doc
