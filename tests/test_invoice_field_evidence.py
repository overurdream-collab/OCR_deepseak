"""Evidence provenance and same-row guards; NO real patients or modified amounts."""
import unittest
from copy import deepcopy
from mdia.invoice_reconciliation import review_document_evidence


def mkdoc():
    vals = [
        ("service_name", "تحليل دم", "تحليل دم", [0.60, 0.30, 0.79, 0.32]),
        ("quantity", "٢", "٢", [0.43, 0.30, 0.46, 0.32]),
        ("unit_price", "10.50", "10.50", [0.31, 0.30, 0.39, 0.32]),
        ("line_total", "21.00", "21.00", [0.12, 0.30, 0.20, 0.32]),
    ]
    item = {"id": "i1", "discount": {"raw": None}}
    evidence = []
    for name, raw, src, bbox in vals:
        eid = "ev_" + name
        item[name] = {"raw": raw, "value": raw, "status": "extracted",
                      "evidence_id": eid, "page": 1, "verification": "unverified"}
        evidence.append({"id": eid, "page": 1, "bbox": bbox, "text": src,
                         "geometry_source": "pdf_text", "word_box_verified": False})
    return {"invoice_items": [item], "evidence": evidence}


class FieldEvidenceTests(unittest.TestCase):
    def test_valid_same_row_has_no_provenance_error(self):
        self.assertEqual(review_document_evidence(mkdoc()), [])

    def test_amount_elsewhere_must_not_validate_field(self):
        d=mkdoc()
        for ev in d["evidence"]:
            if ev["id"]=="ev_unit_price": ev["text"] = "99.99"
        d["evidence"].append({"id":"other", "page":1,"text":"10.50",
                              "bbox":[0.1,0.6,0.2,0.62], "geometry_source":"pdf_text"})
        found=review_document_evidence(d)
        self.assertIn("value_not_in_linked_source",found[0]["field_reasons"]["unit_price"])

    def test_relocated_amount_needs_human_review(self):
        d=mkdoc()
        next(e for e in d["evidence"] if e["id"]=="ev_line_total")["bbox"]=[0.1,0.85,0.2,0.87]
        self.assertIn("cross_row_geometry",review_document_evidence(d)[0]["field_reasons"]["line_total"])

    def test_estimated_geometry_is_not_independent_proof(self):
        d=mkdoc()
        next(e for e in d["evidence"] if e["id"]=="ev_quantity")["geometry_source"]="line_interpolated"
        self.assertIn("estimated_word_location",review_document_evidence(d)[0]["field_reasons"]["quantity"])

    def test_invalid_link_and_bbox(self):
        d=mkdoc()
        d["invoice_items"][0]["quantity"]["evidence_id"]="unrelated"
        next(e for e in d["evidence"] if e["id"]=="ev_line_total")["bbox"]=[-1,0,2,1]
        problems=review_document_evidence(d)[0]["field_reasons"]
        self.assertIn("missing_linked_evidence",problems["quantity"])
        self.assertIn("invalid_source_location",problems["line_total"])

    def test_does_not_change_values(self):
        d=mkdoc()
        d["invoice_items"][0]["line_total"]["raw"]="99999.00"
        before=deepcopy(d)
        found=review_document_evidence(d)
        self.assertEqual(d,before)
        self.assertIn("value_not_in_linked_source",found[0]["field_reasons"]["line_total"])
        self.assertIn("arithmetic_mismatch",found[0]["field_reasons"]["line_total"])

    def test_arabic_decimal_not_digit_substring(self):
        d=mkdoc()
        d["invoice_items"][0]["quantity"]["raw"]="1"
        # Printed '٢' and '10.50' but NOT printed '1'.
        f=review_document_evidence(d)[0]["field_reasons"]["quantity"]
        self.assertIn("value_not_in_linked_source",f)

    def test_missing_value_is_explicit(self):
        d=mkdoc()
        d["invoice_items"][0]["quantity"]["raw"]=None
        d["invoice_items"][0]["quantity"]["status"]="not_found"
        f=review_document_evidence(d)[0]["field_reasons"]["quantity"]
        self.assertIn("missing_extracted_value",f)


if __name__=="__main__":
    unittest.main()
