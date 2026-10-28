"""Conservative recovery of OCR-split Arabic invoice rows (synthetic data only)."""
import unittest
from types import SimpleNamespace

from mdia.extract import extract_document
from mdia.model import Page, Word, build_lines
from mdia.tables import unheaded_arabic_invoice_rows
from mdia.validate import validate_document


def word(text, x0, x1, y0, confidence=0.97):
    return Word(text, x0, y0, x1, y0 + 0.016, confidence, "ocr",
                geometry_source="line_interpolated")


def page(words):
    p = Page(1, 1, 1, method="ocr", words=words)
    p.lines = build_lines(words, p.number)
    return p


class UnheadedArabicFragmentTests(unittest.TestCase):
    def test_numeric_fragment_slightly_below_service_is_recovered(self):
        p = page([
            word("دم", .81, .89, .20), word("تحليل", .91, .99, .20),
            word("2", .55, .58, .212), word("10.50", .37, .45, .212),
            word("21.00", .19, .27, .212),
        ])
        self.assertEqual(len(p.lines), 2)  # OCR delivered two visual lines.
        table = unheaded_arabic_invoice_rows(p)
        self.assertIsNotNone(table)
        self.assertEqual(len(table.rows), 1)
        row = table.rows[0]
        self.assertEqual(len(row.line_idxs), 2)
        self.assertEqual([w.text for w in row.cells["name"]], ["دم", "تحليل"])
        self.assertEqual([row.cells[c][0].text for c in ("qty", "unit_price", "total")],
                         ["2", "10.50", "21.00"])
        self.assertTrue(table.inherited)  # No-header recovery always requires review.
        self.assertEqual(table.line_idxs, set(row.line_idxs))

    def test_end_to_end_extract_has_evidence_and_requires_review(self):
        p = page([
            word("دم", .81, .89, .20), word("تحليل", .91, .99, .20),
            word("2", .55, .58, .212), word("10.50", .37, .45, .212),
            word("21.00", .19, .27, .212),
        ])
        p.flags["ocr_engine"] = "paddleocr-v5-arabic"
        seg = SimpleNamespace(type="hospital_invoice", confidence=1.0, pages=[1], notes=[])
        doc = validate_document(extract_document("synthetic-job", "synthetic-doc", seg, [p], []))
        self.assertEqual(len(doc["invoice_items"]), 1)
        item = doc["invoice_items"][0]
        self.assertEqual(item["service_name"]["raw"], "تحليل دم")
        self.assertEqual([item[f]["value"] for f in ("quantity", "unit_price", "line_total")],
                         [2.0, 10.5, 21.0])
        evidence = {e["id"]: e for e in doc["evidence"]}
        for field in ("service_name", "quantity", "unit_price", "line_total"):
            self.assertIn(item[field]["evidence_id"], evidence)
            self.assertEqual(item[field]["verification"], "needs_review")
        self.assertTrue(doc["requires_human_review"])
        self.assertTrue(any(w["kind"] == "unheaded_invoice_table" for w in doc["warnings"]))

    def test_numeric_fragment_slightly_above_service_is_recovered(self):
        p = page([
            word("كشف", .81, .89, .212), word("استشاري", .90, .98, .212),
            word("1", .55, .58, .20), word("125.00", .35, .45, .20),
            word("125.00", .17, .27, .20),
        ])
        table = unheaded_arabic_invoice_rows(p)
        self.assertEqual(len(table.rows), 1)
        self.assertEqual(len(table.rows[0].line_idxs), 2)

    def test_neighbouring_printed_rows_cannot_be_joined(self):
        p = page([
            word("تحليل", .81, .89, .20), word("دم", .91, .95, .20),
            word("2", .55, .58, .232), word("10.50", .37, .45, .232),
            word("21.00", .19, .27, .232),
        ])
        self.assertIsNone(unheaded_arabic_invoice_rows(p))

    def test_reject_overlapping_unrelated_line_fragments(self):
        p = page([
            word("تحليل", .36, .48, .20), word("دم", .50, .54, .20),
            word("2", .55, .58, .212), word("10.50", .37, .45, .212),
            word("21.00", .19, .27, .212),
        ])
        self.assertIsNone(unheaded_arabic_invoice_rows(p))

    def test_never_turn_invoice_summary_into_service(self):
        p = page([
            word("إجمالي", .82, .91, .20), word("الفاتورة", .92, .99, .20),
            word("1", .55, .58, .212), word("10.50", .37, .45, .212),
            word("21.00", .19, .27, .212),
        ])
        self.assertIsNone(unheaded_arabic_invoice_rows(p))

    def test_ambiguous_fourth_number_is_not_guessed(self):
        p = page([
            word("تحليل", .81, .89, .20), word("دم", .91, .95, .20),
            word("2", .55, .58, .212), word("10.50", .37, .45, .212),
            word("21.00", .19, .27, .212), word("12", .05, .09, .212),
        ])
        self.assertIsNone(unheaded_arabic_invoice_rows(p))


if __name__ == "__main__":
    unittest.main()
