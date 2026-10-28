"""Evidence-bound recovery of a printed invoice identifier inside an OCR token.

Some scans emit 'No:INV-710114' as ONE OCR token. A label-only tokenizer
misses the ID although every character is already present in the source.
This module extracts the literal printed ID, never synthesizes digits or
chooses between conflicting numbers, and never infers any financial amount.
"""
import re

_INVOICE_ID = re.compile(r"(?<![A-Za-z0-9])INV[-‐‑–—][0-9٠-٩۰-۹]{4,12}(?![A-Za-z0-9])",re.I)


def observed_invoice_id(pages):
    """Return (Page, Line, Word, literal_ID) for an unambiguous OCR header ID.

    Bounding boxes are OCR-estimated; if ID is embedded in another token,
    the caller MUST mark that imprecise substring geometry for review.
    """
    matches = []
    for page in pages:
        if page.method != "ocr":
            continue
        for line in page.lines:
            if line.y > 0.28:
                continue
            for word in line.words:
                found = list(_INVOICE_ID.finditer(word.text))
                for m in found:
                    matches.append((page,line,word,m.group(0)))
    if not matches:
        return None
    # Multiple repeats of the exact same header ID on continued pages are
    # fine; different candidate identifiers cannot be resolved by guessing.
    unique = {m[3].lower() for m in matches}
    if len(unique) != 1:
        return None
    return matches[0]
