"""Recover a missing OCR quantity from independent ORIGINAL PDF text.

This only applies to born-digital PDFs that have a valid text layer. It never
divides line_total by price to *create* a number. Printed original-page text
has to contain a single isolated digit physically between the description
and unit price on the exact observed row, matched to both printed amounts.
Scanned PDFs without a real text layer are deliberately left unchanged.
"""
import re
from decimal import Decimal, InvalidOperation

from .textutil import fix_digits, parse_number


def _decimal(value):
    try:
        v = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return None
    return v if v.is_finite() else None


def _bbox(field, evidence):
    source=evidence.get((field or {}).get("evidence_id"))
    b=(source or {}).get("bbox")
    if not isinstance(b,(list,tuple)) or len(b)!=4:
        return None
    if any(not isinstance(x,(int,float)) or x<0 or x>1 for x in b):
        return None
    if not (b[0]<b[2] and b[1]<b[3]):
        return None
    return b


def _box_center_y(b):
    return (b[1]+b[3])/2


def _native_words(pdf_page):
    out=[]
    for w in pdf_page.extract_words():
        try:
            b=[float(w["x0"])/pdf_page.width,
               float(w["top"])/pdf_page.height,
               float(w["x1"])/pdf_page.width,
               float(w["bottom"])/pdf_page.height]
        except (TypeError, ValueError, KeyError, ZeroDivisionError):
            continue
        if (all(0<=x<=1 for x in b) and b[0]<b[2] and b[1]<b[3]
                and isinstance(w.get("text"),str)):
            out.append({"text":w["text"],"bbox":b,
                        "cx":(b[0]+b[2])/2,"cy":(b[1]+b[3])/2})
    return out


def _one_printed_qty(words, name_box, unit_box, total_box, unit_value, total_value):
    """Find one source glyph in a single row; no synthetic truth or inference."""
    y=_box_center_y(unit_box)
    # All three already extracted OCR fields must locate one physical row.
    if abs(_box_center_y(total_box)-y)>.014 or abs(_box_center_y(name_box)-y)>.022:
        return None
    def same_amount(w,box,target):
        return (abs(w["cy"]-y)<=.015
                and abs(w["cx"]-(box[0]+box[2])/2)<=.060
                and parse_number(w["text"])==target)
    if not any(same_amount(w,unit_box,unit_value) for w in words):
        return None
    if not any(same_amount(w,total_box,total_value) for w in words):
        return None

    # Description lies to left of qty for LTR English layouts and to the
    # right of qty for RTL Arabic layouts; the position is independent of
    # arithmetic and is bounded by two source evidence boxes.
    if name_box[2] < unit_box[0]:
        low,high=name_box[2],unit_box[0]
    elif unit_box[2]<name_box[0]:
        low,high=unit_box[2],name_box[0]
    else:
        return None
    if high-low < .012 or high-low > .45:
        return None
    candidates=[]
    for w in words:
        if not (low+.002 < w["cx"] < high-.002 and abs(w["cy"]-y)<.015):
            continue
        token=fix_digits(w["text"].strip())
        if not re.fullmatch(r"[1-9][0-9]?",token):
            continue
        digit=int(token)
        if Decimal(digit)*unit_value != total_value:
            continue
        candidates.append((digit,w))
    # Two adjacent numerals, alternative OCR segments or duplicate evidence
    # are ambiguous; do not borrow a number from a nearby row.
    return candidates[0] if len(candidates)==1 else None


def recover_native_quantities(doc, pdf_path, pages):
    page_map={p.number:p for p in pages}
    ev={e["id"]:e for e in doc.get("evidence",[]) if e.get("id")}
    eligible=[]
    for item in doc.get("invoice_items",[]):
        q=item.get("quantity") or {}
        if q.get("status")=="extracted" and q.get("value") is not None:
            continue
        page_no=item.get("page")
        if page_no not in page_map:
            continue
        p=page_map[page_no]
        if p.flags.get("ocr_engine")!="paddleocr-v5-arabic":
            continue
        name,unit,total=(item.get(k) or {} for k in ("service_name","unit_price","line_total"))
        if not all(v.get("status")=="extracted" for v in (name,unit,total)):
            continue
        nbox,ubox,tbox=(_bbox(x,ev) for x in (name,unit,total))
        u,t=(_decimal(unit.get("value")),_decimal(total.get("value")))
        if not all((nbox,ubox,tbox)) or u is None or t is None or u<=0 or t<=0:
            continue
        eligible.append((item,page_no,nbox,ubox,tbox,u,t))
    if not eligible:
        return doc
    import pdfplumber
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            source_words={}
            for _,num,*_ in eligible:
                if num not in source_words:
                    if num<1 or num>len(pdf.pages):
                        continue
                    source_words[num]=_native_words(pdf.pages[num-1])
    except (OSError,ValueError,RuntimeError):
        return doc

    for item,page_no,nbox,ubox,tbox,unit,total in eligible:
        words=source_words.get(page_no,[])
        candidate=_one_printed_qty(words,nbox,ubox,tbox,unit,total)
        if not candidate:
            continue
        digit,w=candidate
        q=item["quantity"]
        new_id=f"{doc['document_id']}-ev{len(doc['evidence'])+1}"
        doc["evidence"].append({
            "id":new_id,"document_id":doc["document_id"],"page":page_no,
            "text":w["text"],"matched_text":w["text"],
            "bbox":list(w["bbox"]),"bboxes":[list(w["bbox"])],
            "method":"text-layer","geometry_source":"pdf_text",
            "word_box_verified":True,"confidence":1.0,
            "recognizer":"native_pdf_text_layer_same_row",
            "original_ocr_evidence_id":q.get("evidence_id"),
        })
        q["original_ocr_raw"]=q.get("raw")
        q["original_ocr_evidence_id"]=q.get("evidence_id")
        q.update(raw=w["text"],value=float(digit),status="extracted",
                 confidence=1.0,verification="auto_verified",evidence_id=new_id,
                 recovery_method="original_pdf_text_same_row")
        q["review_reasons"]=[x for x in q.get("review_reasons",[]) if x!="unparseable_number"]
    return doc
