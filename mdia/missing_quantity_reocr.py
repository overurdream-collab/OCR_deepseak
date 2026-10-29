"""Re-read a missing printed quantity at its explicit source table column.

No divide-and-fill: require an observed Qty header, same-row description and
both amounts, then two strong reproducible original-pixel digit readings.
"""
import math
from decimal import Decimal, InvalidOperation

from .quantity_reocr import numeric_reocr_crop, choose_digit, _digits
from .textutil import match_key

HEADERS = {match_key(s) for s in ('Qty', 'Quantity', 'الكمية', 'الكميه')}


def _box(field, evidence):
    ev=evidence.get((field or {}).get('evidence_id'),{})
    b=ev.get('bbox')
    if (not isinstance(b,(list,tuple)) or len(b)!=4 or
        any(not isinstance(x,(int,float)) or not math.isfinite(x) or not 0<=x<=1 for x in b)
        or b[0]>=b[2] or b[1]>=b[3]):
        return None
    return b


def recover_missing_quantities(doc,pdf_path,pages,reader=numeric_reocr_crop):
    by_page={p.number:p for p in pages}
    evidence={e['id']:e for e in doc.get('evidence',[]) if e.get('id')}
    for item in doc.get('invoice_items',[]):
        q=item.get('quantity') or {}
        if q.get('status')!='not_found' or q.get('raw') is not None or q.get('value') is not None:
            continue
        p=by_page.get(item.get('page'))
        if p is None or p.flags.get('ocr_engine')!='paddleocr-v5-arabic':continue
        fields=[item.get(k) or {} for k in ('service_name','unit_price','line_total')]
        if any(f.get('status')!='extracted' or f.get('page')!=p.number for f in fields):continue
        boxes=[_box(f,evidence) for f in fields]
        if any(b is None for b in boxes):continue
        n,u,t=boxes
        cy=(u[1]+u[3])/2
        if any(abs((b[1]+b[3])/2-cy)>.012 for b in (n,t)):continue
        if (item.get('discount') or {}).get('status')=='extracted':continue
        try:
            price,total=(Decimal(str(f.get('value'))) for f in fields[1:])
        except (InvalidOperation,ValueError,TypeError):continue
        if not all(x.is_finite() and x>0 for x in (price,total)):continue
        headers=[w for w in p.words if match_key(w.text) in HEADERS
                 and .015<cy-w.cy<.6]
        if not headers:continue
        centers=[w.cx for w in headers]
        if max(centers)-min(centers)>.015:continue
        cx=sum(centers)/len(centers)
        if not .03<cx<.97:continue
        # Header must locate a distinct quantity column, outside ALL observed
        # description/amount regions. No neighboring charge may seed a digit.
        if any(b[0]-.012<=cx<=b[2]+.012 for b in boxes):continue
        half_height=min(.011,max(.005,(u[3]-u[1])/2))
        region=[cx-.012,cy-half_height,cx+.012,cy+half_height]
        try:reads=reader(pdf_path,p.number,region)
        except Exception:continue
        selected=choose_digit(reads,price,total,orig_token=None)
        if not selected:continue
        b=selected.get('bbox')
        if (not isinstance(b,(list,tuple)) or len(b)!=4
            or any(not isinstance(x,(int,float)) or not math.isfinite(x) or not 0<=x<=1 for x in b)
            or not b[0]<b[2] or not b[1]<b[3]
            or abs((b[0]+b[2])/2-cx)>.018
            or abs((b[1]+b[3])/2-cy)>.010):continue
        digit=_digits(selected['text'])
        if digit is None:continue
        eid=f"{doc['document_id']}-ev{len(doc['evidence'])+1}"
        doc['evidence'].append({'id':eid,'document_id':doc['document_id'],'page':p.number,
            'text':selected['text'],'matched_text':selected['text'],'bbox':list(b),'bboxes':[list(b)],
            'method':'ocr','geometry_source':'tesseract_word','word_box_verified':False,
            'confidence':round(selected['confidence'],3),'recognizer':'tesseract_missing_quantity_source_column',
            'source_anchor_evidence_ids':[f['evidence_id'] for f in fields],
            'quantity_header_text':[w.text for w in headers],
            'quantity_header_bboxes':[[w.x0,w.y0,w.x1,w.y1] for w in headers]})
        q.update(raw=selected['text'],value=float(digit),status='extracted',page=p.number,
                 confidence=round(selected['confidence'],3),verification='auto_verified',evidence_id=eid,
                 recovery_method='explicit_quantity_column_independent_pixel_read')
    return doc
