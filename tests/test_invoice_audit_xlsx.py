"""Strict Excel source templates and fail-closed negative controls."""
from io import BytesIO
import unittest
from openpyxl import Workbook

from invoice_audit.xlsx_adapter import audit_xlsx_templates, parse_xlsx_template, LABELS
from invoice_audit import MATCH, EXCEPTION, UNVERIFIABLE
from tests.test_invoice_audit_source import payload


def make_book(kind, quantity="10"):
    source = payload(kind, quantity=quantity)
    wb = Workbook()
    ws = wb.active
    ws.title = "Audit"
    for row, label in LABELS.items():
        ws.cell(row, 1, label)
        if label in source:
            ws.cell(row, 2, source[label])
    for col, title in enumerate(("sku", "unit", "quantity", "unit_price", "line_total"), 1):
        ws.cell(12, col, title)
    for col, label in enumerate(("sku", "unit", "quantity", "unit_price", "line_total"), 1):
        if label in source["lines"][0]:
            ws.cell(13, col, source["lines"][0][label])
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


class ExcelSourceTests(unittest.TestCase):
    def setUp(self):
        self.po = make_book("po")
        self.grn = make_book("grn")
        self.invoice = make_book("invoice")

    def check(self, expected):
        result = audit_xlsx_templates(self.po, self.grn, self.invoice)
        self.assertEqual(result["status"], expected, result)
        self.assertIs(result["approval"], False)
        return result

    def test_exact_source_cells(self):
        result = self.check(MATCH)
        self.assertEqual(result["source_authenticity"], "not_authenticated")
        doc = parse_xlsx_template(self.invoice, "invoice")
        self.assertEqual(doc["lines"][0]["unit_price"]["source_locator"], "xlsx:D13")
        self.assertEqual(doc["lines"][0]["quantity"]["value"], "10")

    def test_mismatched_receipt_is_exception(self):
        self.grn = make_book("grn", quantity="9")
        self.assertIn("QTY_OVER_RECEIVED",
                      {f["rule"] for f in self.check(EXCEPTION)["findings"]})

    def test_corrupt_workbook_unverifiable(self):
        self.invoice = b"not xlsx"
        self.check(UNVERIFIABLE)

    def test_formula_cannot_be_used_for_money(self):
        wb = Workbook()
        ws = wb.active
        ws.title = "Audit"
        for row, label in LABELS.items():
            ws.cell(row, 1, label)
        ws.cell(1, 2, "invoice")
        ws.cell(7, 2, "=SUM(1,2)")
        out = BytesIO()
        wb.save(out)
        self.invoice = out.getvalue()
        self.check(UNVERIFIABLE)

    def test_unexpected_header_field(self):
        wb = Workbook()
        ws = wb.active
        ws.title = "Audit"
        for row, label in LABELS.items():
            ws.cell(row, 1, label)
        ws.cell(1, 2, "po")
        ws.cell(7, 2, "99")  # PO cannot declare an invoice total
        out = BytesIO()
        wb.save(out)
        self.po = out.getvalue()
        self.check(UNVERIFIABLE)


if __name__ == "__main__":
    unittest.main()
