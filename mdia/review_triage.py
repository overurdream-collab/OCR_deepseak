"""Present review triggers separately from OCR errors and provenance advisories.

This module NEVER deletes or downgrades a safety review requirement. It makes
review work actionable by priority and distinguishes word-box verification
from factual/financial corrections. The raw source and original review queue
are untouched.
"""
from collections import Counter

_PROVENANCE = {"paddle_line_geometry_only", "source_estimated_word_location",
               "source_invalid_source_location", "source_missing_linked_evidence",
               "source_cross_row_geometry", "source_value_not_in_linked_source"}
_UNREADABLE = {"unparseable_number", "no_date_found", "invalid_date",
               "ambiguous_day_month_order", "missing_extracted_value"}
_CONFLICT = {"arithmetic_mismatch", "conflicting_values", "multiple_candidates",
             "date_conflict", "incomplete_invoice_item", "incomplete_invoice_items"}
_SCRIPT = {"arabic_ocr_script_variant", "ambiguous_final_farsi_yeh",
           "ocr_extended_arabic_letter", "ocr_arabic_comma_decimal_candidate"}
_MISSING = {"required_field_not_found", "invoice_rows_not_verified"}


def categorize_reasons(reasons):
    terms = set(reasons or ())
    if terms & _MISSING:
        return "missing_input"
    if terms & _CONFLICT:
        return "conflict"
    if terms & _UNREADABLE:
        return "unreadable"
    if terms & _SCRIPT:
        return "script_or_punctuation"
    if terms & _PROVENANCE:
        return "source_evidence"
    return "other_uncertainty"


def triage_document(doc):
    entries = []
    for record in doc.get("requires_human_review", []):
        category = categorize_reasons(record.get("reasons"))
        entries.append({"record_id": record.get("record_id"),
                        "field": record.get("field"),
                        "category": category,
                        "reasons": list(record.get("reasons") or [])})
    counts = Counter(item["category"] for item in entries)
    priorities = ("conflict","unreadable","missing_input",
                  "script_or_punctuation","source_evidence","other_uncertainty")
    result = {
        "all_original_review_items_preserved": True,
        "actionable_reviews": sum(n for k,n in counts.items() if k!="source_evidence"),
        "source_evidence_reviews": counts["source_evidence"],
        "by_category": {k:counts[k] for k in priorities},
        "items": sorted(entries,key=lambda item: priorities.index(item["category"])),
    }
    return result
