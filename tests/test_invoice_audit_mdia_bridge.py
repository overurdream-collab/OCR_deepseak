"""Tests for MDIA bridge: source identity and no OCR -> financial approval."""
import hashlib
import unittest

from invoice_audit.mdia_bridge import prepare_mdia_review, prepare_mdia_review_json


class MDIABridgeTests(unittest.TestCase):
    def setUp(self):
        self.pdf = b"%PDF-1.4\nsynthetic fixture bytes\n"
        self.digest = hashlib.sha256(self.pdf).hexdigest()
        self.field = {"raw": "50.00", "value": 50.0, "page": 1,
                      "evidence_id": "e1", "verification": "auto_verified"}
        self.evidence = {"id": "e1", "page": 1, "matched_text": "50.00",
                         "text": "Price 50.00", "bbox": [.1, .2, .3, .4],
                         "geometry_source": "line_interpolated"}
        self.result = {
            "source": {"sha256": self.digest},
            "documents": [{
                "document_id": "d1", "document_type": "invoice",
                "processing_status": "completed",
                "evidence": [self.evidence],
                "invoices": [{"invoice_total": self.field}],
                "invoice_items": [{"unit_price": self.field}],
            }],
        }

    def test_no_financial_approval_even_when_auto_verified(self):
        out = prepare_mdia_review(self.pdf, self.result)
        self.assertEqual(out["status"], "UNVERIFIABLE")
        self.assertIs(out["approval"], False)
        self.assertTrue(out["documents"][0]["review_required"])
        fld = out["documents"][0]["invoice_items"][0]["fields"]["unit_price"]
        self.assertEqual(fld["status"], "needs_human_review")
        self.assertEqual(fld["source_sha256"], self.digest)
        self.assertEqual(fld["geometry_source"], "line_interpolated")

    def test_source_hash_mismatch_is_blocked(self):
        self.result["source"]["sha256"] = "a" * 64
        out = prepare_mdia_review(self.pdf, self.result)
        self.assertEqual(out["status"], "UNVERIFIABLE")
        self.assertEqual(out["documents"], [])
        self.assertIn("source hash mismatch", out["reasons"][0])

    def test_missing_evidence_unverifiable(self):
        self.result["documents"][0]["evidence"] = []
        fld = prepare_mdia_review(self.pdf, self.result)["documents"][0]["invoices"][0]["fields"]["invoice_total"]
        self.assertEqual(fld["status"], "unverifiable")

    def test_mismatched_page_unverifiable(self):
        self.field["page"] = 2
        fld = prepare_mdia_review(self.pdf, self.result)["documents"][0]["invoices"][0]["fields"]["invoice_total"]
        self.assertEqual(fld["status"], "unverifiable")

    def test_mismatched_raw_text_unverifiable(self):
        self.evidence["matched_text"] = "500.00"
        fld = prepare_mdia_review(self.pdf, self.result)["documents"][0]["invoices"][0]["fields"]["invoice_total"]
        self.assertEqual(fld["status"], "unverifiable")

    def test_reject_non_pdf(self):
        with self.assertRaises(ValueError):
            prepare_mdia_review(b"hello", self.result)

    def test_json_bridge(self):
        import json
        output = prepare_mdia_review_json(self.pdf, json.dumps(self.result).encode())
        self.assertEqual(output["status"], "UNVERIFIABLE")

    def test_invalid_json(self):
        with self.assertRaises(ValueError):
            prepare_mdia_review_json(self.pdf, b"not json")


if __name__ == "__main__":
    unittest.main()
