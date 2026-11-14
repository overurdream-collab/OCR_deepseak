"""Conservative correction of monetary OCR fields from original PDF text-layer tokens.

Only a unique printed amount physically localized at the existing OCR field's
source box can replace a value. No arithmetic is used to create or select an
amount. Ambiguous, split, missing, or spatially displaced tokens fail closed.
"""
from decimal import Decimal, InvalidOperation

from .textutil import parse_number


def _valid_box(box):
    return (isinstance(box, (list, tuple)) and len(box) == 4
            and all(isinstance(x, (int, float)) and 0 <= x <= 1 for x in box)
            and box[0] < box[2] and box[1] < box[3])


def _amount_candidates(words, box):
    """Return unique native-text amounts whose centers lie in a tight field box."""
    x0, y0, x1, y1 = box
    # A little tolerance for text-layer/OCR coordinate drift, but not an entire row.
    pad_x, pad_y = .012, .006
    found = []
    for word in words:
        text = str(word.get("text", "")).strip()
        wb = word.get("bbox")
        if not _valid_box(wb):
            continue
        cx, cy = (wb[0] + wb[2]) / 2, (wb[1] + wb[3]) / 2
        if not (x0 - pad_x <= cx <= x1 + pad_x and y0 - pad_y <= cy <= y1 + pad_y):
            continue
        # A single source token must itself parse as a monetary amount.
        # Never join neighboring tokens or synthesize decimal separators.
        value = parse_number(text)
        if value is None:
            continue
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            continue
        if not amount.is_finite() or amount < 0:
            continue
        found.append((text, amount, list(wb)))
    # Duplicate text-layer spans and multiple plausible amounts are ambiguous.
    distinct = {(x[0], x[1], tuple(x[2])) for x in found}
    return list(distinct)


def recover_native_money(doc, pdf_path, pages):
    """Repair only mismatched OCR money fields with one source-localized PDF token."""
    page_map = {p.number: p for p in pages}
    evidence = {e["id"]: e for e in doc.get("evidence", []) if e.get("id")}
    targets = []
    for item in doc.get("invoice_items", []):
        page_no = item.get("page")
        page = page_map.get(page_no)
        if page is None or page.flags.get("ocr_engine") != "paddleocr-v5-arabic":
            continue
        for key in ("unit_price", "line_total"):
            field = item.get(key) or {}
            if field.get("status") != "extracted" or field.get("value") is None:
                continue
            ev = evidence.get(field.get("evidence_id"))
            if not ev or ev.get("geometry_source") != "line_interpolated":
                continue
            box = ev.get("bbox")
            if not _valid_box(box):
                continue
            try:
                current = Decimal(str(field["value"]))
            except (InvalidOperation, ValueError, TypeError):
                continue
            if not current.is_finite():
                continue
            targets.append((item, key, field, ev, page_no, box, current))
    if not targets:
        return doc

    import pdfplumber
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            source_words = {}
            for _, _, _, _, page_no, _, _ in targets:
                if page_no not in source_words and 1 <= page_no <= len(pdf.pages):
                    p = pdf.pages[page_no - 1]
                    words = []
                    for w in p.extract_words():
                        try:
                            box = [float(w["x0"]) / p.width, float(w["top"]) / p.height,
                                   float(w["x1"]) / p.width, float(w["bottom"]) / p.height]
                        except (TypeError, ValueError, KeyError, ZeroDivisionError):
                            continue
                        if _valid_box(box) and isinstance(w.get("text"), str):
                            words.append({"text": w["text"], "bbox": box})
                    source_words[page_no] = words
    except (OSError, ValueError, RuntimeError):
        return doc

    for item, key, field, old_ev, page_no, box, current in targets:
        candidates = _amount_candidates(source_words.get(page_no, []), box)
        if len(candidates) != 1:
            continue
        raw, amount, source_box = candidates[0]
        if amount == current:
            continue
        new_id = f"{doc['document_id']}-ev{len(doc.get('evidence', [])) + 1}"
        doc.setdefault("evidence", []).append({
            "id": new_id, "document_id": doc["document_id"], "page": page_no,
            "text": raw, "matched_text": raw, "bbox": source_box,
            "bboxes": [source_box], "method": "text-layer",
            "geometry_source": "pdf_text", "word_box_verified": True,
            "confidence": 1.0, "recognizer": "native_pdf_text_layer_monetary_token",
            "original_ocr_evidence_id": old_ev["id"],
        })
        field["original_ocr_raw"] = field.get("raw")
        field["original_ocr_value"] = field.get("value")
        field["original_ocr_evidence_id"] = old_ev["id"]
        field.update(raw=raw, value=float(amount), evidence_id=new_id,
                     confidence=1.0, verification="auto_verified",
                     recovery_method="original_pdf_text_spatial_token")
        field["review_reasons"] = [r for r in field.get("review_reasons", [])
                                   if r not in ("unparseable_number", "ocr_character_confusion")]
        doc.setdefault("warnings", []).append({
            "id": f"{doc['document_id']}-w{len(doc.get('warnings', [])) + 1}",
            "kind": "source_text_money_corrected", "severity": "info",
            "record_id": item.get("id"), "field": key,
            "message": "Monetary OCR value replaced by one uniquely localized original-PDF text token",
            "original_ocr_evidence_id": old_ev["id"], "evidence_ids": [new_id, old_ev["id"]],
        })
    return doc
