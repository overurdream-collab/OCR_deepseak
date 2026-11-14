"""The quality gate must reject a hidden or renamed OCR error."""
import unittest
from scripts.check_zero_error300 import EXPECTED, evaluate_reports


def example():
    results=[]
    # 900 invoice/patient fields + 4*1219 item fields = 5776.
    for i,case in enumerate(sorted(EXPECTED)):
        total=3+4*(5 if i<19 else 4)
        results.append({
            "case":case,"real_paddle_detected":True,"page_failures":[],
            "review_required":False,"human_handoffs":0,"extra_item_rows":0,
            "checks":[{"field":f"field.{j}","matched":True,
                       "actual":j,"linked_evidence":True} for j in range(total)],
            "total":total,"matched":total})
    assert sum(c["total"] for c in results)==5776
    return {
        "status":"completed_real_ocr","seed":20261026,
        "version":"SYNTHETIC-INVOICE-300-HOLDOUT-v1",
        "engines":["paddle_arabic"],"failure_records":[],"results":results
    }


class AbsoluteGateTests(unittest.TestCase):
    def test_no_errors_no_referrals_all_evidenced_passes(self):
        r=evaluate_reports([example()])
        self.assertEqual(r["status"],"PASS")
        self.assertEqual(r["correct"],5776)

    def test_missing_value_blocks(self):
        d=example();c=d["results"][0];c["checks"][0].update(matched=False,actual=None);c["matched"]-=1
        self.assertEqual(evaluate_reports([d])["status"],"BLOCKED")

    def test_wrong_value_blocks_even_when_no_human(self):
        d=example();c=d["results"][0];c["checks"][0]["matched"]=False;c["matched"]-=1
        c["human_handoffs"]=0;c["review_required"]=False
        self.assertEqual(evaluate_reports([d])["status"],"BLOCKED")

    def test_an_unverified_evidence_pointer_blocks(self):
        d=example();d["results"][0]["checks"][0]["linked_evidence"]=False
        self.assertEqual(evaluate_reports([d])["status"],"BLOCKED")

    def test_extra_service_row_blocks(self):
        d=example();d["results"][0]["extra_item_rows"]=1
        self.assertEqual(evaluate_reports([d])["status"],"BLOCKED")

    def test_human_handoff_blocks_even_if_correct(self):
        d=example();d["results"][0]["review_required"]=True
        self.assertEqual(evaluate_reports([d])["status"],"BLOCKED")

    def test_renamed_error_ledger_is_not_a_correction(self):
        d=example();c=d["results"][0];c["checks"][0]["matched"]=False;c["matched"]-=1
        c["machine_unresolved_count"]=1;c["review_required"]=False;c["human_handoffs"]=0
        self.assertEqual(evaluate_reports([d])["status"],"BLOCKED")

    def test_partial_dataset_is_rejected(self):
        d=example();d["results"].pop()
        with self.assertRaises(ValueError):evaluate_reports([d])

    def test_failed_page_is_not_success(self):
        d=example();d["results"][0]["page_failures"]=[1]
        self.assertEqual(evaluate_reports([d])["status"],"BLOCKED")


if __name__=="__main__":
    unittest.main()
