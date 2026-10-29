"""Direct, native-PDF word-evidence fallback for OCR-missing quantities.

Only applies when the original PDF genuinely embeds selectable text.
Scans and image-only files are NOT guessed from arithmetic. No patient
names, prices, totals or row counts are ever changed here.
"""
from decimal import Decimal, InvalidOperation
import math

from .quantity_reocr import _digits
from .textutil import match_key


_HEADER_WORDS = frozenset(("qty", "quantity", "الكمية"))


def _center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def _header_column_x(page):
    candidates = [w.cx for w in page.words
                  if w.y0 < .35 and match_key(w.text.strip(":؛")) in _HEADER_WORDS]
    return candidates[0] if len(candidates) == 1 else None


def _value_evidence(doc, field, index):
    if not field or not field.get("evidence_id"):
        return None
    evidence = index.get(field["evidence_id"])
    if not evidence:
        return None
    bbox = evidence.get("bbox")
    if not isinstance(bbox, (tuple, list)) or len(bbox) != 4:
        return None
    if any(not isinstance(a, (float, int)) or not math.isfinite(a)
           or not 0 <= a <= 1 for a in bbox):
        return None
    if not bbox[0] < bbox[2] or not bbox[1] < bbox[3]:
        return None
    return bbox


def _money(value):
    try:
        v = Decimal(str(value))
        return v if v.is_finite() and v > 0 else None
    except (TypeError, ValueError, InvalidOperation):
        return None


def recover_native_pdf_quantities(doc, pdf_path, pages):
    """Read a uniquely localized, printed quantity digit from PDF text layer.

    * Every candidate digit must be source-visible at the expected column x,
      within the same printed row as separately extracted name, unit price,
      and line amount.
    * Arithmetic is corroboration only, never a source for missing digits.
    * If text layer is absent, ambiguous or conflicts, do nothing.
    """
    import pdfplumber

    page_by_number = {p.number: p for p in pages}
    evidence = {e["id"]: e for e in doc.get("evidence", []) if e.get("id")}
    anchors = {p.number: _header_column_x(p) for p in pages
               if p.method == "ocr"}
    eligible = [it for it in doc.get("invoice_items", [])
                if (it.get("quantity") or {}).get("status") in ("unreadable", "not_found")
                and anchors.get(it.get("page")) is not None]
    if not eligible:
        return doc

    try:
        pdf = pdfplumber.open(str(pdf_path))
    except Exception:
        return doc
    try:
        layer = {}
        for page_number in {it["page"] for it in eligible}:
            if not 1 <= page_number <= len(pdf.pages):
                continue
            source = pdf.pages[page_number - 1]
            if not source.width or not source.height:
                continue
            try:
                words = source.extract_words(x_tolerance=1.5, y_tolerance=3,
                                             keep_blank_chars=False,
                                             use_text_flow=False)
            except Exception:
                continue
            layer[page_number] = [
                (w.get("text", ""), [
                    w["x0"] / source.width, w["top"] / source.height,
                    w["x1"] / source.width, w["bottom"] / source.height])
                for w in words
                if all(k in w for k in ("x0", "top", "x1", "bottom"))
            ]

        for item in eligible:
            page_number = item["page"]
            qty = item["quantity"]
            x_anchor = anchors[page_number]
            name, price, total = (item.get(k) or {}
                                  for k in ("service_name","unit_price","line_total"))
            if not all(f.get("status")=="extracted" and
                       f.get("page")==page_number and f.get("evidence_id")
                       for f in (name,price,total)):
                continue
            if (item.get("discount") or {}).get("status")=="extracted":
                continue
            money_price, money_total = _money(price.get("value")), _money(total.get("value"))
            if money_price is None or money_total is None:
                continue
            boxes = [_value_evidence(doc, f, evidence) for f in (name,price,total)]
            if any(b is None for b in boxes):
                continue
            name_xy, price_xy, total_xy = (_center(b) for b in boxes)
            if (abs(price_xy[1]-total_xy[1])>.025
                or abs(name_xy[1]-price_xy[1])>.040):
                continue
            row_y=(price_xy[1]+total_xy[1])/2
            candidates = []
            for text,box in layer.get(page_number,()):
                digit=_digits(text)
                if digit is None:
                    continue
                x,y=_center(box)
                if (abs(x-x_anchor)<=.052 and abs(y-row_y)<=.018 and
                    Decimal(digit)*money_price==money_total):
                    candidates.append((digit,text,box))
            if len(candidates)!=1:
                continue
            digit,raw,source_bbox = candidates[0]
            # Original PDF text word is the independent source; no OCR letter
            # to digit substitution or template/ground-truth lookup.
            new_eid=f"{doc['document_id']}-ev{len(doc['evidence'])+1}"
            doc["evidence"].append({
                "id":new_eid,"document_id":doc["document_id"],"page":page_number,
                "text":raw,"matched_text":raw,
                "bbox":source_bbox,"bboxes":[source_bbox],
                "method":"text-layer","geometry_source":"pdf_text",
                "word_box_verified":False,"confidence":1.0,
                "recognizer":"original_pdf_embedded_text_quantity"
            })
            qty["original_ocr_raw"]=qty.get("raw")
            qty["original_ocr_evidence_id"]=qty.get("evidence_id")
            qty.update({"raw":raw,"value":float(digit),"status":"extracted",
                        "confidence":1.0,"verification":"auto_verified",
                        "evidence_id":new_eid,"page":page_number,
                        "recovery_method":"direct_original_pdf_text_layer_word"})
            qty["review_reasons"]=[reason for reason in qty.get("review_reasons",[])
                                   if reason not in ("unparseable_number","missing_extracted_value")]
            evidence[new_eid]=doc["evidence"][-1]
    finally:
        pdf.close()
    return doc
