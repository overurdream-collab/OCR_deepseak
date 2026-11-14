"""Ensure crop trial cannot silently re-enable harmful table rotation."""
import unittest
from scripts.run_ppstructure_crop_trial import build_pipeline, extract_json


class CropTrialTests(unittest.TestCase):
    def test_orientation_is_explicitly_disabled(self):
        captured = {}
        def make(**kwargs):
            captured.update(kwargs)
            return "pipeline"
        self.assertEqual(build_pipeline(make), "pipeline")
        self.assertIs(captured["use_table_orientation_classify"], False)
        self.assertEqual(captured["device"], "cpu")
        self.assertIs(captured["use_doc_unwarping"], False)
        self.assertIs(captured["use_doc_orientation_classify"], False)

    def test_preserves_raw_single_prediction(self):
        source = {"res": {"table_res_list": [{"pred_html": "<table></table>"}]}}
        class Result:
            json = source
        class Pipeline:
            def predict(self, path):
                return [Result()]
        self.assertIs(extract_json(Pipeline(), "fake.png"), source)

    def test_rejects_multi_page_results_from_single_crop(self):
        class Result:
            json = {}
        class Pipeline:
            def predict(self, path):
                return [Result(), Result()]
        with self.assertRaisesRegex(ValueError, "exactly one"):
            extract_json(Pipeline(), "fake.png")


if __name__ == "__main__":
    unittest.main()
