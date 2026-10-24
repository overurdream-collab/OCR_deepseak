"""Builds the fixed, documented JSON Schema (draft 2020-12). Run: python -m mdia.schema"""
import json
from pathlib import Path

PATIENT = "name file_no insurance_no age sex date_of_birth".split()
PROVIDER = "facility_name doctor department".split()
HOSP = "admission_date discharge_date length_of_stay_days room_type accommodation_cost".split()
ENTITIES = {
    "invoices": "kind pages invoice_number invoice_date service_date currency subtotal discount_total tax_total additional_fees invoice_total paid_total balance_due patient_share claimed_total",
    "invoice_items": "invoice_id page line_no service_name description service_type service_code service_date quantity unit unit_price discount line_total claimed_amount paid_amount patient_share section",
    "medications": "page source brand_name generic_name strength dosage_form dose route frequency duration quantity_prescribed quantity_dispensed packs unit_price total_price prescription_date prescriber invoice_item_id",
    "diagnoses": "page entry_type text category icd10 certainty diagnosis_date doctor source_document_id",
    "laboratory_tests": "page category test_name result unit reference_range flag test_date price",
    "imaging": "page exam_type region findings exam_date cost",
    "procedures": "page procedure_name procedure_type code date surgeon surgeon_fee anesthesia_fee or_fee supplies_cost total_cost",
}
PLAIN = {"kind", "pages", "invoice_id", "page", "section", "source", "entry_type", "category_plain", "certainty",
         "source_document_id", "invoice_item_id"}
PLAIN_BY_ENTITY = {"diagnoses": {"category", "certainty", "entry_type", "page", "source_document_id"},
                   "laboratory_tests": {"page", "category"}}


def _entity(name, fields):
    props = {"id": {"type": "string", "description": "unique record id"}}
    for f in fields.split():
        plain = f in PLAIN or f in PLAIN_BY_ENTITY.get(name, set())
        if f == "pages":
            props[f] = {"type": "array", "items": {"type": "integer"}}
        elif f == "page":
            props[f] = {"type": "integer"}
        elif plain:
            props[f] = {"type": ["string", "null"]}
        else:
            props[f] = {"$ref": "#/$defs/FieldValue"}
    return {"type": "object", "required": ["id"], "properties": props}


def build():
    fv = {"type": "object", "description": "One extracted field. raw = text exactly as printed; value = normalised value (null when not found/ambiguous); corrected_value only present after a human correction.",
          "required": ["raw", "value", "evidence_id", "page", "confidence", "status", "verification"],
          "properties": {"raw": {"type": ["string", "null"]}, "value": {"type": ["string", "number", "null"]},
                         "evidence_id": {"type": ["string", "null"]}, "page": {"type": ["integer", "null"]},
                         "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                         "status": {"enum": ["extracted", "not_found", "unreadable", "ambiguous"]},
                         "verification": {"enum": ["unverified", "auto_verified", "needs_review", "corrected", "not_applicable"]},
                         "review_reasons": {"type": "array", "items": {"type": "string"}},
                         "alternatives": {"type": "array", "items": {"type": "object"}},
                         "corrected_value": {}}}
    ev = {"type": "object", "required": ["id", "document_id", "page", "text", "matched_text", "bbox", "method", "confidence"],
          "properties": {"id": {"type": "string"}, "document_id": {"type": "string"}, "page": {"type": "integer"},
                         "text": {"type": "string", "description": "full source line/row text"},
                         "matched_text": {"type": "string"},
                         "bbox": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4,
                                  "description": "[x0,y0,x1,y1] relative to page width/height, origin top-left"},
                         "bboxes": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
                         "method": {"enum": ["text-layer", "ocr"]}, "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                         "geometry_source": {"enum": ["pdf_text", "tesseract_word", "line_interpolated", "cross_engine_word_match"]},
                         "word_box_verified": {"type": "boolean"}}}
    warn = {"type": "object", "required": ["id", "kind", "severity", "message"],
            "properties": {"id": {"type": "string"}, "kind": {"type": "string"}, "severity": {"enum": ["info", "warning", "error"]},
                           "message": {"type": "string"}}}
    review = {"type": "object", "required": ["record_id", "field", "confidence", "reasons"],
              "properties": {"record_id": {"type": "string"}, "field": {"type": "string"}, "raw": {"type": ["string", "null"]},
                             "evidence_id": {"type": ["string", "null"]}, "page": {"type": ["integer", "null"]},
                             "confidence": {"type": "number"}, "reasons": {"type": "array", "items": {"type": "string"}}}}
    group = lambda names: {"type": "object", "properties": {n: {"$ref": "#/$defs/FieldValue"} for n in names}}
    doc_props = {
        "document_id": {"type": "string"}, "document_type": {"type": "string"},
        "processing_status": {"enum": ["completed", "completed_with_review", "failed"]},
        "pages": {"type": "array", "items": {"type": "integer"}},
        "patient": group(PATIENT), "provider": group(PROVIDER), "hospitalization": group(HOSP),
        "evidence": {"type": "array", "items": {"$ref": "#/$defs/Evidence"}},
        "warnings": {"type": "array", "items": {"$ref": "#/$defs/Warning"}},
        "requires_human_review": {"type": "array", "items": {"$ref": "#/$defs/ReviewItem"}},
    }
    for k in ENTITIES:
        doc_props[k] = {"type": "array", "items": {"$ref": f"#/$defs/{k}_record"}}
    defs = {"FieldValue": fv, "Evidence": ev, "Warning": warn, "ReviewItem": review,
            "Document": {"type": "object", "required": ["document_id", "document_type", "processing_status", "patient", "provider", "invoices",
                                                        "invoice_items", "medications", "diagnoses", "laboratory_tests", "imaging", "procedures",
                                                        "hospitalization", "evidence", "warnings", "requires_human_review"],
                         "properties": doc_props}}
    for k, f in ENTITIES.items():
        defs[f"{k}_record"] = _entity(k, f)
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "https://mdia.local/schema/1.0",
            "title": "MDIA extraction result", "type": "object",
            "required": ["schema_version", "job_id", "source", "processing_status", "documents", "document_links", "summary"],
            "properties": {"schema_version": {"const": "1.0"}, "job_id": {"type": "string"}, "source": {"type": "object"},
                           "processing_status": {"enum": ["completed", "completed_with_review", "completed_with_errors"]},
                           "documents": {"type": "array", "items": {"$ref": "#/$defs/Document"}},
                           "document_links": {"type": "array", "items": {"type": "object"}},
                           "page_info": {"type": "array"}, "summary": {"type": "object"}},
            "$defs": defs}


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "schema" / "mdia.schema.json"
    out.write_text(json.dumps(build(), ensure_ascii=False, indent=2), "utf-8")
    print("wrote", out)
