import unittest

from scripts.select_teacher_pilot30 import manifest, select_cases


class TeacherPilotSelectionTests(unittest.TestCase):
    def test_stratified_and_unique(self):
        cases = select_cases()
        self.assertEqual(len(cases), 30)
        self.assertEqual(len({c["id"] for c in cases}), 30)
        self.assertEqual(len({c["layout"] for c in cases}), 6)
        self.assertEqual(len({c["representation"] for c in cases}), 6)

    def test_holdout_not_training(self):
        result = manifest()
        self.assertEqual(result["purpose"], "EVALUATION_ONLY_NOT_FOR_TRAINING")
        self.assertTrue(result["synthetic"])
        self.assertEqual(result["count"], 30)
        self.assertTrue(all(len(c["case_metadata_sha256"]) == 64 for c in result["cases"]))


if __name__ == "__main__":
    unittest.main()
