"""Zero human handoffs must NEVER falsely approve unreadable medical bills.

The goal is zero referrals, not fake 100% extraction accuracy. The machine-only
ledger must keep errors and financial exposure visible while withholding
unverified output from downstream import/export.
"""
import copy
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mdia.zero_human import apply_zero_human_policy, record_machine_issue
from mdia.schema import build


def field(value="3", *, status="extracted", verification="auto_verified", raw=None):
    return {
        "raw": str(value) if raw is None and value is not None else raw,
        "value": value, "status": status,
        "verification": verification, "page": 1,
        "confidence": .97, "evidence_id": "source-word-1"
    }


def invoice_doc():
    return {
        "document_id": "synthetic-d1",
        "document_type": "hospital_invoice",
        "processing_status": "completed_with_review",
        "pages": [1],
        "patient": {"name": field("مريم"), "insurance_no": field("XZ1")},
        "provider": {}, "hospitalization": {},
        "invoices": [{"id": "invoice1", "invoice_number": field("INV-1001"),
                      "invoice_total": field(120)}],
        "invoice_items": [{"id": "item1", "service_name": field("فحص"),
                           "quantity": field(3), "unit_price": field(40),
                           "line_total": field(120)}],
        "medications": [], "diagnoses": [], "laboratory_tests": [],
        "imaging": [], "procedures": [],
        "warnings": [],
        "evidence": [{"id": "source-word-1", "method": "ocr",
                      "matched_text": "3"}],
        "requires_human_review": [],
    }


class ZeroHumanPolicyTests(unittest.TestCase):
    def test_missing_quantity_creates_machine_blocker_not_a_human_referral(self):
        d = invoice_doc()
        q = d["invoice_items"][0]["quantity"]
        q.update(raw="w", value=None, status="unreadable",
                 verification="needs_review",
                 review_reasons=["unparseable_number"])
        d["requires_human_review"] = [
            {"record_id": "item1", "field": "quantity", "raw": "w",
             "page": 1, "confidence": .4, "evidence_id": "source-word-1",
             "reasons": ["unparseable_number"]}]
        apply_zero_human_policy(d)
        self.assertEqual(d["requires_human_review"], [])
        self.assertEqual(d["human_handoff_count"], 0)
        self.assertFalse(d["extraction_ready"])
        self.assertFalse(d["financial_approval"])
        self.assertEqual(d["processing_status"], "blocked_unresolved")
        self.assertEqual(q["raw"], "w")
        self.assertIsNone(q["value"])
        self.assertEqual(q["verification"], "machine_unresolved")
        self.assertEqual(q["original_verification"], "needs_review")
        self.assertEqual(d["machine_unresolved_checks"][0]["field"], "quantity")
        self.assertEqual(d["machine_unresolved_checks"][0]["resolution_state"],
                         "unresolved_machine_only")
        self.assertEqual(d["machine_unresolved_checks"][0]["automatic_retries_executed"], 0)

    def test_unflagged_missing_financial_input_never_silently_succeeds(self):
        d = invoice_doc()
        d["invoice_items"][0]["unit_price"].update(
            raw=None, value=None, status="not_found", verification="not_applicable")
        apply_zero_human_policy(d)
        self.assertEqual(d["processing_status"], "blocked_unresolved")
        self.assertIn("required_financial_field_missing",
                      d["machine_unresolved_checks"][0]["reasons"])
        self.assertEqual(d["machine_unresolved_checks"][0]["field"], "unit_price")

    def test_source_word_geometry_warning_blocks_even_if_all_text_is_correct(self):
        d=invoice_doc()
        d["requires_human_review"]=[{
            "record_id":"synthetic-d1", "field":"ocr_word_bbox",
            "page":1,"confidence":0,"raw":None, "evidence_id":None,
            "reasons":["paddle_line_geometry_only"]}]
        apply_zero_human_policy(d)
        self.assertEqual(d["human_handoff_count"],0)
        self.assertEqual(d["unresolved_machine_count"],1)
        self.assertEqual(d["machine_unresolved_checks"][0]["category"],"source_evidence")
        self.assertFalse(d["extraction_ready"])

    def test_no_false_block_on_fully_evidenced_invoice(self):
        d=invoice_doc()
        d["processing_status"]="completed"
        apply_zero_human_policy(d)
        self.assertEqual(d["processing_status"], "completed")
        self.assertTrue(d["extraction_ready"])
        self.assertFalse(d["financial_approval"])
        self.assertEqual(d["machine_unresolved_checks"], [])
        self.assertEqual(d["human_handoff_count"], 0)

    def test_errors_block_even_without_review_record(self):
        d=invoice_doc()
        d["warnings"].append({"kind":"line_arithmetic_mismatch","severity":"error"})
        apply_zero_human_policy(d)
        self.assertFalse(d["extraction_ready"])
        self.assertEqual(d["processing_status"],"blocked_unresolved")

    def test_missing_all_item_rows_is_a_blocker(self):
        d=invoice_doc()
        d["invoice_items"]=[]
        apply_zero_human_policy(d)
        self.assertFalse(d["extraction_ready"])
        self.assertEqual(d["machine_unresolved_checks"][0]["field"],"invoice_items")

    def test_failed_extraction_is_not_reported_as_completed(self):
        d=invoice_doc()
        d["processing_status"]="failed"
        apply_zero_human_policy(d)
        self.assertFalse(d["extraction_ready"])
        self.assertEqual(d["processing_status"],"failed")

    def test_idempotent_and_source_values_unchanged(self):
        d=invoice_doc()
        d["requires_human_review"]=[{
            "record_id":"invoice1","field":"invoice_total",
            "reasons":["arithmetic_mismatch"],"raw":"120",
            "page":1,"confidence":.8,"evidence_id":"source-word-1"}]
        source=copy.deepcopy(d["evidence"])
        apply_zero_human_policy(d)
        previous=copy.deepcopy(d)
        apply_zero_human_policy(d)
        self.assertEqual(d,previous)
        self.assertEqual(d["evidence"],source)
        self.assertEqual(d["invoices"][0]["invoice_total"]["value"],120)

    def test_record_late_cross_document_conflict_as_machine_blocker(self):
        d=invoice_doc()
        apply_zero_human_policy(d)
        record_machine_issue(d,"cross_document_identity","cross_document_identity_conflict")
        record_machine_issue(d,"cross_document_identity","cross_document_identity_conflict")
        self.assertEqual(len(d["machine_unresolved_checks"]),1)
        self.assertFalse(d["extraction_ready"])
        self.assertEqual(d["human_handoff_count"],0)

    def test_schema_explicitly_supports_machine_blocks(self):
        s=build()
        self.assertIn("blocked_unresolved",s["properties"]["processing_status"]["enum"])
        ds=s["$defs"]["Document"]
        self.assertIn("blocked_unresolved", ds["properties"]["processing_status"]["enum"])
        self.assertIn("machine_unresolved",s["$defs"]["FieldValue"]["properties"]["verification"]["enum"])

    def test_legacy_default_remains_available_until_pilot_proven(self):
        from mdia.pipeline import process_job
        self.assertIn("zero_human",process_job.__code__.co_varnames)

    def test_pipeline_zero_human_keeps_machine_blockers_in_job_summary(self):
        from mdia.pipeline import process_job
        from mdia import pipeline
        d=invoice_doc()
        d["invoice_items"][0]["quantity"].update(
            raw="H", value=None, status="unreadable", verification="needs_review",
            review_reasons=["unparseable_number"])
        d["requires_human_review"]=[{"record_id":"item1","field":"quantity",
                                     "reasons":["unparseable_number"],"raw":"H",
                                     "confidence":.3,"evidence_id":"source-word-1","page":1}]
        page=SimpleNamespace(number=1,flags={"ocr_engine":"paddleocr-v5-arabic"},
              warnings=[],method="ocr",image=None,width=600,height=800)
        seg=SimpleNamespace(type="hospital_invoice",confidence=1,pages=[1])
        class StoreStub:
            saved=None
            def status(self,j):return {"filename":"synthetic.pdf","sha256":"abc"}
            def set_status(self,*a,**kw):return None
            def path(self,*a):return Path("/tmp/synthetic-test.pdf")
            def save_result(self,j,result):self.saved=result
        store=StoreStub()
        def fake_validate(doc):return doc
        with patch.object(pipeline,"read_document",return_value=[page]), \\
             patch.object(pipeline,"classify_page",return_value="mock"), \\
             patch.object(pipeline,"segment",return_value=[seg]), \\
             patch.object(pipeline,"extract_document",return_value=d), \\
             patch.object(pipeline,"validate_document",side_effect=fake_validate), \\
             patch("mdia.quantity_reocr.recover_quantities",return_value=None), \\
             patch("mdia.service_spacing.repair_document_service_names",return_value=None):
            result=process_job(store,"synthetic-job",zero_human=True)
        self.assertIsNotNone(result)
        self.assertEqual(result["processing_status"],"blocked_unresolved")
        self.assertEqual(result["summary"]["human_handoffs"],0)
        self.assertGreaterEqual(result["summary"]["machine_unresolved_checks"],1)
        self.assertEqual(result["documents"][0]["requires_human_review"],[])
        self.assertFalse(result["documents"][0]["extraction_ready"])


if __name__=="__main__":
    unittest.main()
