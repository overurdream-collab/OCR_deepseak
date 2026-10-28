"""Independent, LOCAL recovery of a misread OCR quantity using original PDF pixels.

Never derive a charge from arithmetic. Arithmetic only corroborates a numeral
already recognized by Tesseract in the original source crop. Fail closed if
independent recognition is weak, conflicting, unavailable or geometrically
ambiguous. Does not use APIs, cloud services, patient metadata or ground truth.
"""
from decimal import Decimal, InvalidOperation
import math
import re

from .textutil import fix_digits

# A stringent opt-in class of errors: Paddle misrecognized a quantity glyph
# as ASCII M, while 2+ other row fields are separately visible and parseable.
CONFLICT_CONFIDENCE = 0.80
ACCEPT_CONFIDENCE = 0.85
MIN_CORROBORATION = 0.65


def _digits(text):
    token = fix_digits(str(text or "").strip())
    if not re.fullmatch(r"[0-9]{1,2}", token):
        return None
    value = int(token)
    return value if 1 <= value <= 99 else None


def numeric_reocr_crop(pdf_path, page_no, source_box):
    """Return independent OCR attempts on exact original PDF pixels.

    Each attempt contains read text, confidence and a word-level bbox mapped
    from Tesseract's word detection to original PDF page-relative coordinates.
    No approximate Paddle token bbox is ever reported as new word evidence.
    """
    import pypdfium2 as pdfium
    import pytesseract
    from pytesseract import Output
    from PIL import ImageOps

    if (len(source_box) != 4 or
        any(not isinstance(x,(float,int)) or not math.isfinite(x) or x<0 or x>1 for x in source_box)):
        return []
    x0,y0,x1,y1=source_box
    if x0>=x1 or y0>=y1 or x1-x0>.12 or y1-y0>.06:
        return []
    pdf=pdfium.PdfDocument(str(pdf_path))
    if not (1<=page_no<=len(pdf)):
        return []
    page=pdf[page_no-1]
    from . import config
    img=page.render(scale=config.OCR_DPI/72).to_pil().convert("RGB")
    W,H=img.size
    px=max(.005,(x1-x0)*.55)
    py=max(.003,(y1-y0)*.60)
    a,b,c,d=(max(0,int((x0-px)*W)), max(0,int((y0-py)*H)),
             min(W,int((x1+px)*W)), min(H,int((y1+py)*H)))
    if c-a<8 or d-b<8:return []
    source_crop=img.crop((a,b,c,d))
    reads=[]
    # An input with only one quantity glyph, never a full adjacent price row.
    for mode in ("original","contrast4x"):
        if mode=="original":
            crop=source_crop
            scale=1
        else:
            gray=ImageOps.autocontrast(source_crop.convert("L"))
            crop=gray.resize((gray.width*4,gray.height*4))
            scale=4
        for lang,psm in (("eng",10),("ara+eng",10),("ara+eng",13)):
            try:
                data=pytesseract.image_to_data(
                    crop,lang=lang,
                    config=f"--oem 1 --psm {psm} -c tessedit_char_whitelist=0123456789٠١٢٣٤٥٦٧٨٩",
                    output_type=Output.DICT)
            except (pytesseract.TesseractError, OSError):
                continue
            recognized=[]
            for i,tok in enumerate(data.get("text",[])):
                raw=str(tok).strip()
                if not raw:continue
                try:
                    conf=float(data["conf"][i])
                    left,top,width,height=(float(data[k][i]) for k in ("left","top","width","height"))
                except (ValueError,TypeError,IndexError,KeyError):
                    continue
                if not math.isfinite(conf) or not 0 <= conf <= 100 or width<=0 or height<=0:
                    continue
                rect=[(a+left/scale)/W,(b+top/scale)/H,
                      (a+(left+width)/scale)/W,(b+(top+height)/scale)/H]
                if any(z<0 or z>1 for z in rect):continue
                recognized.append({"text":raw,"confidence":conf/100,"bbox":rect})
            if len(recognized)==1:
                read=recognized[0]
                read.update({"mode":mode,"lang":lang,"psm":psm})
                reads.append(read)
    return reads


def choose_digit(reads, price, total, orig_token="M"):
    """Approve only source-read integer corroborated by printed row arithmetic.

    No arithmetic-only inference; no two different high-conf OCR digits.
    The same Tesseract model across preprocessing modes isn't independent
    proof twice, so at least one actual high-conf OCR output is mandatory.
    """
    if orig_token!="M":
        return None
    try:
        price=Decimal(str(price))
        total=Decimal(str(total))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not (price>0 and total>0 and price.is_finite() and total.is_finite()):
        return None
    candidates=[]
    for read in reads:
        if not isinstance(read,dict):continue
        num=_digits(read.get("text"))
        conf=read.get("confidence",0)
        if num is None or not isinstance(conf,(float,int)) or not math.isfinite(conf):
            continue
        if not 0 <= conf <= 1:continue
        candidates.append((num,conf,read))
    strong=[x for x in candidates if x[1]>=CONFLICT_CONFIDENCE]
    if len({x[0] for x in strong})>1:
        return None
    agreeing=[x for x in candidates if x[1]>=MIN_CORROBORATION and x[0]*price==total]
    if not agreeing or max(x[1] for x in agreeing)<ACCEPT_CONFIDENCE:
        return None
    # A disagreement even if slightly below the acceptance threshold is
    # evidence of ambiguity, not a reason to pick the convenient number.
    winning=max(agreeing,key=lambda x:x[1])
    if any(x[0]!=winning[0] and x[1]>=CONFLICT_CONFIDENCE for x in candidates):
        return None
    return winning[2]


def recover_quantities(doc, pdf_path, pages, reader=numeric_reocr_crop):
    """Resolve a Paddle M only when another OCR actually reads its glyph.

    The original Paddle evidence remains in the document. A new linked evidence
    entry contains the secondary OCR's word-level original-PDF coordinates.
    Financial decisions are still outside MDIA's extraction remit.
    """
    by_page={p.number:p for p in pages}
    evidence={e["id"]:e for e in doc.get("evidence",[]) if e.get("id")}
    for item in doc.get("invoice_items",[]):
        qty=item.get("quantity",{})
        if qty.get("raw")!="M" or qty.get("status")!="unreadable":
            continue
        page_no=qty.get("page")
        source_page=by_page.get(page_no)
        if source_page is None or source_page.flags.get("ocr_engine")!="paddleocr-v5-arabic":
            continue
        original_evidence=evidence.get(qty.get("evidence_id"))
        if not original_evidence or original_evidence.get("matched_text")!="M":
            continue
        if original_evidence.get("geometry_source")!="line_interpolated":
            continue
        # No discount, no post-hoc invoice-total substitution or inferred row.
        if (item.get("discount") or {}).get("status")=="extracted":
            continue
        p,t=(item.get(k) or {} for k in ("unit_price","line_total"))
        if (p.get("status")!="extracted" or t.get("status")!="extracted" or
            p.get("page")!=page_no or t.get("page")!=page_no or
            not p.get("evidence_id") or not t.get("evidence_id")):
            continue
        source_box=original_evidence.get("bbox")
        if not isinstance(source_box,(list,tuple)):
            continue
        try:
            reads=reader(pdf_path,page_no,source_box)
        except Exception:
            # Offline secondary OCR may be unavailable; don't break invoice.
            continue
        selected=choose_digit(reads,p.get("value"),t.get("value"),qty["raw"])
        if selected is None:continue
        digit=_digits(selected["text"])
        if digit is None:continue
        box=selected.get("bbox")
        if (not isinstance(box,(list,tuple)) or len(box)!=4 or
            any(not isinstance(z,(float,int)) or z<0 or z>1 for z in box) or
            not box[0]<box[2] or not box[1]<box[3]):
            continue
        # The SECOND OCR located an independent numeral INSIDE the same
        # candidate source region, not a token borrowed from an adjacent row.
        midy=(box[1]+box[3])/2
        source_mid=(source_box[1]+source_box[3])/2
        if abs(midy-source_mid)>.025:
            continue
        new_eid=f"{doc['document_id']}-ev{len(doc['evidence'])+1}"
        doc["evidence"].append({
            "id":new_eid,"document_id":doc["document_id"],
            "page":page_no,"text":selected["text"],"matched_text":selected["text"],
            "bbox":list(box),"bboxes":[list(box)],"method":"ocr",
            "geometry_source":"tesseract_word","word_box_verified":False,
            "confidence":round(selected["confidence"],3),
            "recognizer":"tesseract_secondary_original_pdf_crop",
            "original_ocr_evidence_id":original_evidence["id"],
        })
        qty["original_ocr_raw"]=qty["raw"]
        qty["original_ocr_evidence_id"]=original_evidence["id"]
        qty["raw"]=selected["text"]
        qty["value"]=float(digit)
        qty["status"]="extracted"
        qty["confidence"]=round(selected["confidence"],3)
        qty["verification"]="auto_verified"
        qty["review_reasons"]=[r for r in qty.get("review_reasons",[])
                                if r!="unparseable_number"]
        qty["recovery_method"]="independent_local_ocr_plus_same_row_arithmetic"
        qty["evidence_id"]=new_eid
        doc["warnings"].append({
            "id":f"{doc['document_id']}-w{len(doc['warnings'])+1}",
            "kind":"secondary_ocr_quantity_recovered",
            "severity":"info","record_id":item.get("id"),
            "message":"Unreadable OCR quantity confirmed by local secondary OCR and printed row arithmetic",
            "original_ocr_evidence_id":original_evidence["id"],"evidence_ids":[new_eid,original_evidence["id"]],
        })
    return doc
