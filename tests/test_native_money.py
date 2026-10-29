"""Tests for strict source-localized native PDF monetary recovery."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mdia.native_money import _amount_candidates, recover_native_money


def word(text, x0, y0=.20, x1=None, y1=.22):
    return {"text": text, "bbox": [x0, y0, x1 if x1 is not None else x0 + .04, y1]}


class NativeMoneyTests(unittest.TestCase):
    def test_unique_amount_inside_source_box_is_found(self):
        result = _amount_candidates([word("48.00", .50, x1=.56)], [.49, .19, .57, .23])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "48.00")

    def test_adjacent_row_amount_is_excluded(self):
        result = _amount_candidates([word("48.00", .50, y0=.26, y1=.28)], [.49, .19, .57, .23])
        self.assertEqual(result, [])

    def test_multiple_amounts_fail_closed(self):
        result = _amount_candidates([word("48.00", .50, x1=.56), word("4800", .50, x1=.55)],
                                    [.49, .19, .57, .23])
        self.assertEqual(len(result), 2)

    def test_split_decimal_tokens_are_not_joined_or_guessed(self):
        result = _amount_candidates([word("48", .50, x1=.52), word(".00", .523, x1=.55)],
                                    [.49, .19, .57, .23])
        self.assertEqual(len(result), 0)

    def document(self):
        return {"document_id": "d1", "evidence": [
            {"id": "price-ev", "bbox": [.49, .19, .57, .23], "geometry_source": "line_interpolated"}],
            "warnings": [], "invoice_items": [{
                "id": "row1", "page": 1,
                "unit_price": {"raw": "4800", "value": 4800., "status": "extracted",
                               "evidence_id": "price-ev", "page": 1},
                "line_total": {"status": "not_found"}}]}

    def test_integration_replaces_only_with_unique_spatial_source_token(self):
        d = self.document()
        class P:
            width = height = 1000
            def extract_words(self):
                return [{"text": "48.00", "x0": 500, "top": 200, "x1": 560, "bottom": 220}]
        class PDF:
            pages = [P()]
            def __enter__(self): return self
            def __exit__(self, *_): return False
        with patch("pdfplumber.open", return_value=PDF()):
            recover_native_money(d, "x.pdf", [SimpleNamespace(number=1, flags={"ocr_engine": "paddleocr-v5-arabic"})])
        f = d["invoice_items"][0]["unit_price"]
        self.assertEqual(f["value"], 48.0)
        self.assertEqual(f["original_ocr_value"], 4800.)
        self.assertEqual(d["evidence"][-1]["geometry_source"], "pdf_text")

    def test_scanned_or_non_paddle_input_does_not_change_document(self):
        d = self.document()
        before = copy.deepcopy(d)
        recover_native_money(d, "x.pdf", [SimpleNamespace(number=1, flags={})])
        self.assertEqual(d, before)


if __name__ == "__main__":
    unittest.main()
