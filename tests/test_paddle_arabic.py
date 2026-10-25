"""Pure-Python mocked tests for optional PaddleOCR adapter (no Paddle model download)."""
import sys
import types
import unittest
from unittest.mock import patch

from mdia import paddle_arabic as p


class PaddleArabicTests(unittest.TestCase):
    def test_english_and_arabic_positions(self):
        results = [{'res': {'rec_texts': ['اسم المريض خالد يوسف', 'Total 2500'],
                            'rec_scores': [0.96, 0.9],
                            'rec_boxes': [[100, 20, 460, 60], [20, 80, 280, 110]]}}]
        words = p.result_to_words(results, (500, 200))
        self.assertEqual([w.text for w in words], ['اسم', 'المريض', 'خالد', 'يوسف', 'Total', '2500'])
        self.assertEqual([w.conf for w in words], [0.96] * 4 + [0.9] * 2)
        self.assertGreater(words[0].x0, words[1].x0)
        self.assertLess(words[4].x0, words[5].x0)
        self.assertTrue(all(w.method == 'ocr' for w in words))
        self.assertTrue(all(w.box is None for w in words))

    def test_polygon_boxes_and_array_like(self):
        class ArrayLike:
            def __init__(self, data): self.data = data
            def tolist(self): return self.data
        data = [{'res': {'rec_texts': ['الفاتورة 123'],
                         'rec_scores': [0.82],
                         'rec_polys': ArrayLike([[[8, 10], [90, 10], [90, 30], [8, 30]]])}}]
        self.assertEqual(len(p.result_to_words(data, (100, 50))), 2)

    def test_refuse_missing_evidence(self):
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            p.result_to_words([{'res': {'rec_texts': ['أدوية'], 'rec_scores': [0.8]}}], (200, 200))

    def test_refuse_misaligned_arrays(self):
        with self.assertRaisesRegex(ValueError, 'Misaligned'):
            p.result_to_words([{'res': {'rec_texts': ['a'], 'rec_scores': [], 'rec_boxes': [[1, 1, 10, 10]]}}], (200, 200))

    def test_no_false_model_fallback(self):
        p._load_model.cache_clear()
        with patch.dict(sys.modules, {'paddleocr': None}):
            with self.assertRaisesRegex(RuntimeError, 'not installed'):
                p._load_model()
        p._load_model.cache_clear()

    def test_model_name_explicit_and_lazy(self):
        p._load_model.cache_clear()
        seen = {}
        class Model:
            def __init__(self, **kw): seen.update(kw)
        with patch.dict(sys.modules, {'paddleocr': types.SimpleNamespace(PaddleOCR=Model)}):
            p._load_model()
        self.assertEqual(seen['text_recognition_model_name'], p.MODEL_NAME)
        self.assertEqual(seen['device'], 'cpu')
        p._load_model.cache_clear()


class PaddleReaderIntegration(unittest.TestCase):
    def test_opt_in_engine_and_cache_are_isolated(self):
        import tempfile
        from pathlib import Path
        from mdia.reader import read_document
        from mdia.model import Word
        from tests.arabic_samples import invoice
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / 'fixture.pdf'
            invoice(pdf, 'shaped')
            fake = [Word('فاتورة', .75, .2, .92, .23, 0.98, 'ocr')]
            with patch.dict('os.environ', {'MDIA_OCR_ENGINE': 'paddle_arabic'}):
                with patch('mdia.paddle_arabic.ocr_image', return_value=fake) as call:
                    pages = read_document(pdf, root / 'cache', ocr_mode='force')
            self.assertEqual(pages[0].flags['ocr_engine'], 'paddleocr-v5-arabic')
            self.assertEqual(pages[0].words[0].text, 'فاتورة')
            self.assertTrue(any(x['kind'] == 'paddle_line_geometry_only' for x in pages[0].warnings))
            self.assertTrue(call.called)
            with patch.dict('os.environ', {'MDIA_OCR_ENGINE': 'tesseract'}):
                with patch('mdia.reader.ocr_page', return_value=[Word('TESS',.1,.1,.2,.2,.9,'ocr')]) as tess:
                    next_pages = read_document(pdf, root / 'cache', ocr_mode='force')
            self.assertTrue(tess.called)
            self.assertEqual(next_pages[0].words[0].text, 'TESS')

    def test_reject_unknown_engine(self):
        import tempfile
        from pathlib import Path
        from mdia.reader import read_document
        with tempfile.TemporaryDirectory() as t:
            with patch.dict('os.environ', {'MDIA_OCR_ENGINE': 'typo'}):
                with self.assertRaisesRegex(ValueError, 'Unsupported'):
                    read_document(Path(t) / 'irrelevant.pdf', Path(t) / 'cache')


if __name__ == '__main__':
    unittest.main()
