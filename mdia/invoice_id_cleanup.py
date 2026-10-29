"""Recover literal printed invoice identifier when OCR appends stray digit.

This does not create or normalize digits. Only a *standalone, independently
visible* OCR token in the original printed header may replace the malformed
value, and the original full raw text/evidence stays preserved.
"""
import re
from .invoice_identifier import observed_invoice_id

_MALFORMED = re.compile(
    r"(?i)^(INV[-‐‑–—][0-9٠-٩۰-۹]{4,12})\s+([0-9٠-٩۰-۹])$"
)


def repair_invoice_id(current, source_pages, ctx):
    if current.get("status")!="extracted" or not isinstance(current.get("raw"),str):
        return current
    m=_MALFORMED.fullmatch(current["raw"].strip())
    if not m:
        return current
    hit=observed_invoice_id(source_pages)
    if hit is None:
        return current
    page,line,word,literal=hit
    # A substring of a merged OCR token is NOT sufficient to prove where the
    # intended identifier ends. Demand exact independent printed word token.
    if word.text != literal or literal.casefold()!=m.group(1).casefold():
        return current
    # The source header must be on the same page as the malformed reading.
    if page.number != current.get("page"):
        return current
    fresh=ctx.field(page,[word],raw=literal,source=line.text)
    if fresh.get("value") != literal or not fresh.get("evidence_id"):
        return current
    fresh["original_ocr_raw"]=current["raw"]
    fresh["original_ocr_evidence_id"]=current.get("evidence_id")
    fresh["recovery_method"]="standalone_printed_invoice_identifier"
    return fresh
