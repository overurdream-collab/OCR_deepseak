"""Keyword-evidence page classifier + segmentation of a PDF into logical documents."""
import re
from dataclasses import dataclass, field
from typing import List

from .model import Page
from .textutil import fix_digits, nfkc

TYPES = ["hospital_invoice", "clinic_invoice", "pharmacy_invoice", "prescription", "medical_report",
         "surgical_report", "discharge_summary", "lab_result", "radiology_report", "approval_request",
         "services_statement", "payment_receipt", "account_statement", "unknown"]

# (regex on canonical text, weight)
_RULES = {
    "lab_result": [(r"\blaborator", 3), (r"\blab (result|report)", 4), (r"reference range|ref\.? range", 3), (r"\bhematology|biochemistry|\bcbc\b", 2),
                   (r"مختبر", 3), (r"نتيجه التحليل|نتائج التحاليل|نتايج", 4), (r"المجال المرجعي|القيم الطبيعيه", 3)],
    "radiology_report": [(r"radiology|x-?ray|\bmri\b|\bct scan|ultrasound|sonograph|mammogra|doppler", 3), (r"\bimpression\b|\bfindings\b", 2),
                         (r"تقرير اشعه|اشعه|الاشعه|رنين|مقطعيه|موجات فوق الصوتيه|سونار", 3), (r"الانطباع", 2)],
    "prescription": [(r"prescription|\brx\b|\bsig\b", 4), (r"الوصفه الطبيه|وصفه طبيه|روشته|وصفه", 4)],
    "surgical_report": [(r"operative (report|note)|operation (report|note)|surgical report", 5), (r"\bsurgeon\b|anesthesi|anaesthesi", 2),
                        (r"تقرير عمليه|تقرير العمليه|العمليه الجراحيه|تقرير جراحي", 4), (r"الجراح|التخدير", 2)],
    "discharge_summary": [(r"discharge (summary|report)|summary of discharge", 6), (r"discharge", 2),
                          (r"ملخص الخروج|تقرير الخروج|تقرير خروج|خروج من المستشفى", 6)],
    "approval_request": [(r"pre-?authori[sz]ation|prior approval|approval request|authori[sz]ation request", 6),
                         (r"طلب موافقه|موافقه مسبقه|طلب الموافقه", 6)],
    "services_statement": [(r"statement of services|services statement|service statement", 6), (r"كشف الخدمات|كشف خدمات", 6)],
    "payment_receipt": [(r"payment receipt|\breceipt\b", 5), (r"سند قبض|ايصال دفع|ايصال استلام|\bايصال\b|سند صرف", 5)],
    "account_statement": [(r"statement of account|account statement", 6), (r"كشف حساب|كشف الحساب", 6)],
    "medical_report": [(r"medical report|clinical report|clinic note|progress note", 5), (r"التقرير الطبي|تقرير طبي|تقرير حاله", 5),
                       (r"\bdiagnosis\b|chief complaint", 1), (r"التشخيص|الشكوى", 1)],
    "_invoice": [(r"\binvoice\b|\bbill\b|tax invoice", 5), (r"فاتوره", 5), (r"subtotal|grand total|balance due", 1),
                 (r"الاجمالي|المجموع", 1)],
}
_PHARM = re.compile(r"pharmacy|صيدليه")
_HOSP = re.compile(r"hospital|مستشفى")
_CLIN = re.compile(r"clinic|polyclinic|medical center|عياده|مجمع طبي|مركز طبي")
_INV_NO = re.compile(r"(?i)(?:invoice|inv|bill)\s*(?:no|number|#)\.?\s*[:\-]?\s*([A-Za-z0-9\-/]+)|رقم الفاتوره\s*[:\-]?\s*([A-Za-z0-9\-/]+)")


@dataclass
class PageClass:
    type: str
    confidence: float
    scores: dict
    invoice_no: str = ""
    page_of: tuple = ()


def _canon(page: Page):
    head = " \n".join(_simple(l.text) for l in page.lines[:8])
    body = " \n".join(_simple(l.text) for l in page.lines)
    return head, body


def _simple(s):
    s = fix_digits(nfkc(s))
    s = re.sub("[\u064B-\u065F\u0640\u0670]", "", s)
    s = re.sub("[أإآٱ]", "ا", s).replace("ى", "ي").replace("ة", "ه")
    return s.lower()


def classify_page(page: Page) -> PageClass:
    head, body = _canon(page)
    scores = {}
    for t, rules in _RULES.items():
        sc = 0.0
        for rx, w in rules:
            if re.search(rx, head):
                sc += w * 2
            elif re.search(rx, body):
                sc += w
        scores[t] = sc
    inv = scores.pop("_invoice")
    if inv >= 5:
        if _PHARM.search(head) or (_PHARM.search(body) and not _HOSP.search(body)):
            scores["pharmacy_invoice"] = inv + 2
        elif _CLIN.search(head) or (_CLIN.search(body) and not _HOSP.search(body)):
            scores["clinic_invoice"] = inv + 1
        else:
            scores["hospital_invoice"] = inv + (1 if _HOSP.search(body) else 0)
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top, second = ranked[0], ranked[1] if len(ranked) > 1 else ("", 0)
    if top[1] < 3:
        t, conf = "unknown", 0.0
    else:
        t = top[0]
        conf = round(min(1.0, (top[1] - second[1]) / max(top[1], 1) * 0.7 + min(top[1], 10) / 10 * 0.3), 3)
    m = _INV_NO.search(page.text)
    inv_no = (m.group(1) or m.group(2) or "") if m else ""
    po = re.search(r"(?i)(?:page|صفحه)\s*(\d+)\s*(?:of|من|/)\s*(\d+)", _simple(page.text))
    return PageClass(t, conf, {k: v for k, v in scores.items() if v}, inv_no.strip(), tuple(map(int, po.groups())) if po else ())


@dataclass
class DocSegment:
    pages: List[int]
    type: str
    confidence: float
    invoice_no: str = ""
    notes: list = field(default_factory=list)


def segment(pages: List[Page], classes: List[PageClass]) -> List[DocSegment]:
    segs: List[DocSegment] = []
    for p, c in zip(pages, classes):
        cur = segs[-1] if segs else None
        new = cur is None
        invoice_like = lambda t: t.endswith("_invoice")
        if cur and not new:
            same_type = c.type == cur.type or (invoice_like(c.type) and invoice_like(cur.type))
            if c.type == "unknown" or (c.confidence < 0.35 and c.type != cur.type and not c.invoice_no):
                new = False                                    # continuation of current document
            elif not same_type:
                new = True
            elif c.invoice_no and cur.invoice_no and c.invoice_no != cur.invoice_no:
                new = True                                     # same type, different invoice number
            elif c.page_of and c.page_of[0] == 1 and cur.type == c.type:
                new = True
        if new:
            segs.append(DocSegment([p.number], c.type, c.confidence, c.invoice_no))
        else:
            cur.pages.append(p.number)
            if c.type == "unknown":
                cur.notes.append(f"page {p.number}: no strong type cues, treated as continuation")
            if not cur.invoice_no and c.invoice_no:
                cur.invoice_no = c.invoice_no
            if cur.type == "unknown" and c.type != "unknown":
                cur.type, cur.confidence = c.type, c.confidence
    return segs
