"""Teacher pilot tests run offline and use synthetic fixtures only."""
import tempfile
import unittest
from pathlib import Path

from mdia.teacher_labels import TeacherLabelError, make_manifest, page_texts


class TeacherLabelsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "synthetic.png"
        self.source.write_bytes(b"synthetic-test-only")
        self.response = {
            "object": "ocr.result", "page_count": 1,
            "pages": [{"index": 0, "text": "كمية ٢ السعر 12", "finish_reason": "stop"}]
        }

    def test_exact_ground_truth_candidate_only(self):
        truth = {"synthetic": True, "fields": {"quantity": "٢", "price": "12", "name": "سالم"}}
        result = make_manifest(self.source, truth, self.response, "السعر 12")
        self.assertFalse(result["training_ready"])
        self.assertEqual([x["field"] for x in result["approved_exact_truth_candidates"]],
                         ["price", "quantity"])
        self.assertEqual(result["teacher_missing_truth"][0]["field"], "name")

    def test_no_real_records(self):
        with self.assertRaises(TeacherLabelError):
            make_manifest(self.source, {"synthetic": False, "fields": {"a": "b"}},
                          self.response, "")

    def test_truncated_page_rejected(self):
        self.response["pages"][0]["finish_reason"] = "length"
        with self.assertRaises(TeacherLabelError):
            page_texts(self.response)

    def test_page_order_rejected(self):
        self.response["pages"][0]["index"] = 1
        with self.assertRaises(TeacherLabelError):
            page_texts(self.response)

    def test_missing_truth_rejected(self):
        with self.assertRaises(TeacherLabelError):
            make_manifest(self.source, {"synthetic": True}, self.response, "")


if __name__ == "__main__":
    unittest.main()
