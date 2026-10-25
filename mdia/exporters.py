"""Exports: JSON, CSV (zip of tables), Excel, PDF report.

PDF rule (non-negotiable): Arabic text uses an Arabic-capable TTF (Amiri preferred), is reshaped with
arabic_reshaper and reordered with bidi.algorithm.get_display, and the finished PDF is re-read and
verified; if Arabic glyphs are missing the export FAILS instead of delivering unreadable symbols."""
import csv
import io
import json
import re
import zipfile
from pathlib import Path

from . import config
from .textutil import has_ar

ENTITIES = [("invoices", "invoices"), ("invoice_items", "invoice_items"), ("medications", "medications"),
            ("diagnoses", "diagnoses"), ("laboratory_tests", "laboratory_tests"), ("imaging", "imaging"),
            ("procedures", "procedures")]
SKIP_KEYS = {"id", "page", "pages", "kind", "section", "source", "invoice_id", "invoice_item_id", "entry_type",
             "category", "certainty", "source_document_id"}


def best(f):
    """corrected value > normalised value > raw."""
    if not isinstance(f, dict) or "status" not in f:
        return f
    if "corrected_value" in f:
        return f["corrected_value"]
    return f["value"] if f["value"] is not None else f["raw"]


def _flatten(doc_id, rec):
    row = {"document_id": doc_id, "record_id": rec.get("id", "")}
    for k, v in rec.items():
        if isinstance(v, list):
            row[k] = ",".join(map(str, v))
        elif isinstance(v, dict) and "status" in v:
            row[k] = best(v)
            row[k + "_raw"] = v["raw"]
            row[k + "_page"] = v["page"]
            row[k + "_confidence"] = v["confidence"]
            row[k + "_verification"] = v["verification"]
        elif k in SKIP_KEYS or k == "id":
            row[k] = v if k != "id" else row["record_id"]
    row.pop("id", None)
    return row


def tables(result):
    out = {}
    for key, name in ENTITIES:
        rows = [_flatten(d["document_id"], r) for d in result["documents"] for r in d[key]]
        out[name] = rows
    singles = []
    for d in result["documents"]:
        for group in ("patient", "provider", "hospitalization"):
            for k, f in (d.get(group) or {}).items():
                if f.get("status") != "not_found" or "corrected_value" in f:
                    singles.append({"document_id": d["document_id"], "document_type": d["document_type"], "group": group, "field": k,
                                    "value": best(f), "raw": f["raw"], "page": f["page"], "confidence": f["confidence"],
                                    "verification": f["verification"]})
    out["general_info"] = singles
    out["warnings"] = [{"document_id": d["document_id"], **{k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
                                                              for k, v in w.items()}} for d in result["documents"] for w in d["warnings"]]
    out["review_queue"] = [{"document_id": d["document_id"], **{k: (",".join(map(str, v)) if isinstance(v, list) else v) for k, v in q.items()}}
                           for d in result["documents"] for q in d["requires_human_review"]]
    out["evidence"] = [{**{k: v for k, v in e.items() if k not in ("bboxes", "bbox")}, "bbox": json.dumps(e["bbox"])}
                       for d in result["documents"] for e in d["evidence"]]
    return out


def to_json(result) -> bytes:
    return json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")


def to_csv_zip(result) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, rows in tables(result).items():
            if not rows:
                continue
            cols = list(dict.fromkeys(k for r in rows for k in r))
            s = io.StringIO()
            w = csv.DictWriter(s, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
            z.writestr(f"{name}.csv", "\ufeff" + s.getvalue())      # BOM so Excel on Windows opens Arabic correctly
    return buf.getvalue()


def to_xlsx(result) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in tables(result).items():
        ws = wb.create_sheet(name[:31])
        ws.sheet_view.rightToLeft = False
        if not rows:
            ws.append(["(empty)"])
            continue
        cols = list(dict.fromkeys(k for r in rows for k in r))
        ws.append(cols)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F4E79")
        for r in rows:
            ws.append([r.get(c) for c in cols])
        ws.freeze_panes = "A2"
        for i, c in enumerate(cols, 1):
            width = min(60, max(len(str(c)), *(len(str(r.get(c, ""))) for r in rows[:200])) + 2)
            ws.column_dimensions[ws.cell(1, i).column_letter].width = width
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ----------------------------------------------------------------------- PDF
class PdfExportError(Exception):
    pass


def find_arabic_font():
    names = ["Amiri-Regular.ttf", "Amiri.ttf", "NotoNaskhArabic-Regular.ttf", "NotoSansArabic-Regular.ttf",
             "Scheherazade-Regular.ttf", "arial.ttf", "tahoma.ttf", "DejaVuSans.ttf"]
    for n in names:
        for root in config.FONT_DIRS:
            if root.exists():
                hit = next(root.rglob(n), None)
                if hit:
                    return hit
    return None


def _shape(text: str) -> str:
    """Arabic reshaping + bidi reordering (required before drawing in ReportLab)."""
    text = "" if text is None else str(text)
    if not has_ar(text):
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError as e:
        raise PdfExportError("تصدير PDF بالعربية يتطلب arabic-reshaper و python-bidi / Arabic PDF export requires "
                             "arabic-reshaper and python-bidi (pip install -r requirements.txt)") from e
    return get_display(arabic_reshaper.reshape(text))


def to_pdf(result) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font_path = find_arabic_font()
    if not font_path:
        raise PdfExportError("لم يوجد خط عربي (ضع Amiri-Regular.ttf في مجلد fonts) / no Arabic font found: put Amiri-Regular.ttf in ./fonts")
    pdfmetrics.registerFont(TTFont("MDIA", str(font_path)))
    face = pdfmetrics.getFont("MDIA").face
    covered = set(face.charToGlyph)

    expected_ar = []

    def S(text, maxlen=90):
        t = "" if text is None else str(text)
        t = t if len(t) <= maxlen else t[:maxlen - 1] + "…"
        shaped = _shape(t)
        missing = {c for c in shaped if ord(c) > 127 and ord(c) not in covered and not c.isspace()}
        if missing:
            raise PdfExportError(f"الخط {font_path.name} لا يحتوي الرموز: {''.join(sorted(missing))[:20]} / font lacks glyphs")
        if has_ar(t):
            expected_ar.append(shaped)
        return shaped

    base = ParagraphStyle("b", fontName="MDIA", fontSize=8.5, leading=11)
    h1 = ParagraphStyle("h1", parent=base, fontSize=15, leading=19, spaceAfter=6)
    h2 = ParagraphStyle("h2", parent=base, fontSize=11.5, leading=15, spaceBefore=8, spaceAfter=3)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24,
                            title="MDIA report")
    story = [Paragraph(S("تقرير الاستخراج الطبي — Medical Document Intelligence Agent"), h1),
             Paragraph(S(f"الملف: {result['source']['filename']}   |   Job: {result['job_id']}   |   الحالة: {result['processing_status']}"), base),
             Spacer(1, 6)]
    T = tables(result)
    title_map = {"general_info": "معلومات عامة / General", "invoices": "الفواتير / Invoices", "invoice_items": "بنود الفواتير / Invoice items",
                 "medications": "الأدوية / Medications", "diagnoses": "التشخيصات / Diagnoses",
                 "laboratory_tests": "التحاليل / Laboratory", "imaging": "الأشعة / Imaging", "procedures": "الإجراءات / Procedures",
                 "warnings": "التحذيرات / Warnings", "review_queue": "تتطلب مراجعة / Needs review"}
    for name, title in title_map.items():
        rows = T.get(name) or []
        story.append(Paragraph(S(title), h2))
        if not rows:
            story.append(Paragraph(S("— لا يوجد / none —"), base))
            continue
        cols = [c for c in dict.fromkeys(k for r in rows for k in r)
                if not c.endswith(("_page", "_verification")) and c not in ("record_id",)][:11]
        data = [[Paragraph(S(c, 24), base) for c in cols]]
        for r in rows[:300]:
            data.append([Paragraph(S(r.get(c, ""), 70), base) for c in cols])
        t = Table(data, repeatRows=1, colWidths=[(landscape(A4)[0] - 48) / len(cols)] * len(cols))
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE6F1")), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(t)
    doc.build(story)
    pdf_bytes = buf.getvalue()
    _verify_pdf_arabic(pdf_bytes, expected_ar)
    return pdf_bytes


def _verify_pdf_arabic(pdf_bytes: bytes, expected_shaped):
    """Re-read the PDF: Arabic glyphs must be present and no replacement/box characters may appear."""
    if not expected_shaped:
        return
    import pdfplumber
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = "".join((p.extract_text() or "") for p in pdf.pages)
    want = sum(1 for s in expected_shaped for c in s if "\u0600" <= c <= "\u06FF" or "\uFB50" <= c <= "\uFEFF")
    got = sum(1 for c in text if "\u0600" <= c <= "\u06FF" or "\uFB50" <= c <= "\uFEFF")
    if "\ufffd" in text or "■" in text or "(cid:" in text or got < 0.9 * want:
        raise PdfExportError(f"فشل التحقق من العربية في PDF (متوقع≈{want} حرفًا، وُجد {got}) / Arabic verification failed")
