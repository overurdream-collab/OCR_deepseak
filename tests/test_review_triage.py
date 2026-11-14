"""Review queue classification must not hide human/safety checks."""
import unittest
from mdia.review_triage import categorize_reasons,triage_document

class ReviewTriageTests(unittest.TestCase):
    def test_geometry_is_separate_from_actual_errors(self):
        q=[
            {"record_id":"doc1","field":"ocr_word_bbox","reasons":["paddle_line_geometry_only"]},
            {"record_id":"it1","field":"quantity","reasons":["unparseable_number"]},
            {"record_id":"it1","field":"unit_price","reasons":["arithmetic_mismatch"]},
            {"record_id":"doc1","field":"patient.name","reasons":["ambiguous_final_farsi_yeh"]},
        ]
        result=triage_document({"requires_human_review":q})
        self.assertEqual(result["actionable_reviews"],3)
        self.assertEqual(result["source_evidence_reviews"],1)
        self.assertEqual(result["by_category"]["unreadable"],1)
        self.assertEqual(result["by_category"]["conflict"],1)
        self.assertEqual(result["by_category"]["script_or_punctuation"],1)
        self.assertEqual(result["items"][0]["field"],"unit_price")
        self.assertEqual(len(q),4)
        self.assertTrue(result["all_original_review_items_preserved"])

    def test_missing_item_row_is_not_silently_approved(self):
        q=[{"record_id":"invoice","field":"invoice_items",
            "reasons":["invoice_rows_not_verified"]}]
        res=triage_document({"requires_human_review":q})
        self.assertEqual(res["by_category"]["missing_input"],1)
        self.assertEqual(res["actionable_reviews"],1)

    def test_no_review_does_not_require_human(self):
        res=triage_document({"requires_human_review":[]})
        self.assertEqual(res["actionable_reviews"],0)
        self.assertEqual(res["source_evidence_reviews"],0)

    def test_multiple_reasons_prefer_actual_conflict(self):
        self.assertEqual(categorize_reasons(
            ["source_estimated_word_location","arithmetic_mismatch"]),"conflict")


if __name__=="__main__":
    unittest.main()
