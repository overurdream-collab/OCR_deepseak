"""Tesseract vs REAL Paddle PP-OCRv5 Arabic on identical synthetic page pixels.

Measures raw-text presence only (NOT structured medical field accuracy).
Real Paddle inference is required; no fake numbers or OCR fallback.
"""
import argparse
import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path

import pypdfium2 as pdfium

from mdia.paddle_arabic import MODEL_NAME, ocr_image
from mdia.reader import ocr_page
from mdia.model import build_lines
from tests import arabic_samples


FIXTURES = {
    'invoice_shaped.pdf': ('invoice', 'shaped', ['رقم الفاتورة', 'INV-4004', 'خالد يوسف', 'كشف استشاري', 'تحليل دم شامل', 'الكمية', '1,250.00', '75.50', '1,401.00']),
    'invoice_visual.pdf': ('invoice', 'visual', ['رقم الفاتورة', 'INV-4004', 'خالد يوسف', 'كشف استشاري', 'تحليل دم شامل', 'الكمية', '1,250.00', '75.50', '1,401.00']),
    'prescription_shaped.pdf': ('prescription', 'shaped', ['وصفة طبية', 'سارة عمر', 'أموكسيسيلين', 'باراسيتامول', '٥٠٠', 'مرتين يوميا', '٣ أيام']),
}


def norm(value):
    s = unicodedata.normalize('NFKC', str(value))
    s = re.sub('[\u064B-\u065F\u0640]', '', s)
    s = s.translate(str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789'))
    s = re.sub(r'(?<=\d),(?=\d{3}(?:[.,]|$))', '', s)  # remove grouping commas only
    return re.sub(r'\s+', '', s).lower()


def hits(text, expected):
    return {t: norm(t) in norm(text) for t in expected}


def prepare(out):
    out.mkdir(parents=True, exist_ok=True)
    for name, (type_, mode, _) in FIXTURES.items():
        if type_ == 'invoice':
            arabic_samples.invoice(out / name, mode)
        else:
            arabic_samples.prescription(out / name, mode)


def run(dest, fixtures=None, scale=3.0):
    dest = Path(dest)
    folder = Path(fixtures) if fixtures else dest.parent / 'synthetic_pdf'
    prepare(folder)
    output = {'status': 'incomplete', 'source': 'synthetic_generated', 'paddle_model': MODEL_NAME,
              'metric': 'normalized substring presence in raw OCR output; NOT financial or medical extraction accuracy',
              'samples': []}
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        for filename, (_, __, expected) in FIXTURES.items():
            raw_pdf = (folder / filename).read_bytes()
            page = pdfium.PdfDocument(str(folder / filename))[0]
            image = page.render(scale=scale).to_pil().convert('RGB')
            record = {'pdf': filename, 'sha256': hashlib.sha256(raw_pdf).hexdigest(), 'checks': expected,
                      'readings': {}}
            for engine in ('tesseract', 'paddleocr_v5_arabic'):
                start = time.monotonic()
                words = ocr_page(image, 'ara+eng') if engine == 'tesseract' else ocr_image(image)
                text = '\n'.join(line.text for line in build_lines(words, 1))
                chk = hits(text, expected)
                record['readings'][engine] = {'duration_seconds': round(time.monotonic() - start, 3),
                    'matched': sum(chk.values()), 'expected': len(chk), 'by_field': chk,
                    'raw_text': text, 'recognized_segments': len(words),
                    'geometry': 'Paddle line rectangles; token positions interpolated' if engine != 'tesseract' else 'Tesseract word boxes'}
            output['samples'].append(record)
            print(filename, *(f'{e}: {record["readings"][e]["matched"]}/{len(expected)}' for e in record['readings']))
        output['status'] = 'executed_both_models'
    except Exception as exc:
        output['status'] = 'failed'
        output['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        dest.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Result:', dest, '| status:', output['status'])
    return output


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', default='results/paddle_arabic_vs_tesseract.json')
    p.add_argument('--fixtures', default=None)
    args = p.parse_args()
    run(args.output, args.fixtures)
