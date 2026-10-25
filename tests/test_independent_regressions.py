"""Independent synthetic-layout regressions: never real medical or insurance records."""
import tempfile
import unittest
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from mdia.kv import line_pairs
from mdia.model import Page, Word, build_lines
from mdia.pipeline import process_job
from mdia.store import Store
from mdia.tables import _candidate_lines, _STOP_WORDS, unheaded_arabic_invoice_rows


def synthetic_pdf(path, lines):
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont('Helvetica', 11)
    y = A4[1]-75
    for line in lines:
        c.drawString(45, y, line)
        y -= 25
    c.save()


def process_pdf(path):
    with tempfile.TemporaryDirectory(prefix='mdia_regression_') as tmp:
        store = Store(Path(tmp))
        jid = store.create(path.name, path.read_bytes())
        result = process_job(store, jid, ocr_mode='off')
        if result is None:
            raise AssertionError(store.status(jid))
        return result


class IndependentRegressions(unittest.TestCase):
    def test_stop_tokens_are_not_single_letters(self):
        self.assertNotIn('d', _STOP_WORDS)
        self.assertNotIn('t', _STOP_WORDS)
        self.assertIn('signature', _STOP_WORDS)

    def test_full_name_and_both_invoice_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'independent_bill.pdf'
            synthetic_pdf(p, [
                'Meridian Health Center',
                'BILL - MEDICAL SERVICES',
                'Bill Number: MH-26-017',
                'Customer: Test Patient Four',
                'Description             Qty             Rate             Amount',
                'Electrocardiogram         1             850.00            850.00',
                'Vitamin D Test           2             1100.00           2200.00',
                'Grand Total: 3050.00 YER',
            ])
            d = process_pdf(p)['documents'][0]
            self.assertEqual(d['patient']['name']['raw'], 'Test Patient Four')
            self.assertEqual([x['service_name']['raw'] for x in d['invoice_items']],
                             ['Electrocardiogram', 'Vitamin D Test'])

    def test_two_rx_lines_without_and_with_strength(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'independent_rx.pdf'
            synthetic_pdf(p, [
                'MEDICAL PRESCRIPTION',
                'Name: Test Patient Four',
                'Suspected diagnosis: viral rhinitis',
                'Rx: Cetirizine 10 mg tablet, oral, once daily for 7 days',
                'Rx: saline nasal spray PRN',
            ])
            d=process_pdf(p)['documents'][0]
            self.assertEqual(d['patient']['name']['raw'], 'Test Patient Four')
            self.assertEqual([m['brand_name']['raw'] for m in d['medications']],
                             ['Cetirizine', 'saline nasal spray'])
            self.assertEqual(d['medications'][1]['strength']['status'], 'not_found')

    def test_scanned_arabic_unheaded_ocr_rows_requires_review(self):
        words = [
            Word('استشارة',.84,.32,.94,.34,.95,'ocr'),
            Word('1',.70,.32,.73,.34,.95,'ocr'),
            Word('2500',.56,.32,.62,.34,.95,'ocr'),
            Word('2500',.41,.32,.46,.34,.95,'ocr'),
            Word('تحليل',.88,.37,.95,.39,.95,'ocr'),
            Word('سكر',.80,.37,.87,.39,.95,'ocr'),
            Word('1',.70,.37,.73,.39,.95,'ocr'),
            Word('800',.56,.37,.62,.39,.95,'ocr'),
            Word('800',.41,.37,.46,.39,.95,'ocr'),
        ]
        page = Page(1,595,842,'ocr',words)
        page.lines=build_lines(words,1)
        t=unheaded_arabic_invoice_rows(page)
        self.assertIsNotNone(t)
        self.assertEqual(len(t.rows),2)
        self.assertTrue(t.inherited)
        self.assertEqual([w.text for w in t.rows[0].cells['qty']],['1'])
        self.assertEqual([w.text for w in t.rows[1].cells['total']],['800'])

    def test_unheaded_row_without_three_prices_is_not_invented(self):
        words=[Word('استشارة',.8,.1,.92,.12,.95,'ocr'), Word('1',.7,.1,.72,.12,.95,'ocr'),
               Word('2500',.4,.1,.46,.12,.95,'ocr')]
        page=Page(1,595,842,'ocr',words)
        page.lines=build_lines(words,1)
        self.assertIsNone(unheaded_arabic_invoice_rows(page))


if __name__=='__main__':
    unittest.main()
