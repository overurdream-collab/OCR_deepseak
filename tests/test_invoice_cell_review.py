"""Ambiguity must survive extraction, arithmetic checks and the review queue."""
import tempfile
import unittest
from pathlib import Path

from mdia.model import Word
from mdia.tables import invoice_cell_review_reasons
from mdia.pipeline import process_job
from mdia.store import Store
from tests.make_samples import Doc


def words(*tokens):
    return [Word(t, .1 + i * .04, .2, .13 + i * .04, .22) for i, t in enumerate(tokens)]


class CellReviewTests(unittest.TestCase):
    def test_currency_and_negative_parentheses_are_not_ambiguous(self):
        self.assertEqual(invoice_cell_review_reasons({
            "qty": words("2"), "unit_price": words("SAR", "(20.00)"),
            "total": words("٤٠٫٠٠", "ريال")}), {})

    def test_unknown_text_and_split_digits_are_not_silently_accepted(self):
        for tokens in (("1", "00"), ("unknown", "10"), ("10O",)):
            self.assertIn("total", invoice_cell_review_reasons({"total": words(*tokens)}))

    def test_all_financial_columns_are_checked(self):
        for key in ("qty", "unit_price", "total", "discount", "claimed", "paid", "patient_share"):
            self.assertIn(key, invoice_cell_review_reasons({key: words("1", "2")}))

    def test_row_is_kept_and_matching_arithmetic_cannot_clear_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invoice.pdf"
            d = Doc(path)
            d.line("Sample Medical Hospital")
            d.line("Invoice No: REVIEW-123")
            d.line("Patient Name: Sample Person")
            for x, label in ((40, "Description"), (300, "Qty"), (360, "Unit Price"), (460, "Total")):
                d.t(x, d.y, label)
            d.y -= 20
            for x, value in ((40, "Consultation"), (300, "1 2"), (360, "10.00"), (460, "120.00")):
                d.t(x, d.y, value)
            d.y -= 25
            d.t(360, d.y, "Total"); d.t(460, d.y, "120.00")
            d.save()
            store = Store(Path(tmp) / "store")
            jid = store.create(path.name, path.read_bytes())
            result = process_job(store, jid, ocr_mode="off")
            doc = result["documents"][0]
            self.assertEqual(len(doc["invoice_items"]), 1)
            item = doc["invoice_items"][0]
            self.assertEqual(item["service_name"]["value"], "Consultation")
            self.assertEqual(item["line_total"]["value"], 120.0)
            self.assertEqual(item["quantity"]["verification"], "needs_review")
            self.assertEqual(item["service_name"]["verification"], "needs_review")
            self.assertEqual(doc["invoices"][0]["invoice_total"]["verification"], "needs_review")
            warning = next(w for w in doc["warnings"] if w["kind"] == "ambiguous_invoice_cell")
            self.assertEqual(warning["cell_raw"], "1 2")
            evidence = next(e for e in doc["evidence"] if e["id"] == warning["evidence_ids"][0])
            self.assertEqual(evidence["matched_text"], "1 2")
            self.assertTrue(any(q["record_id"] == item["id"] and q["field"] == "quantity"
                                for q in doc["requires_human_review"]))
