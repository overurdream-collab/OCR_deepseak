import json
from pathlib import Path

import fitz

from src.pilot import evaluate, normalize


ROOT = Path(__file__).resolve().parents[1]


def test_dataset_four_pdfs():
    gt = json.loads((ROOT / 'samples' / 'ground_truth.json').read_text(encoding='utf-8'))
    assert len(gt) == 4
    for filename in gt:
        with fitz.open(ROOT / 'samples' / filename) as doc:
            assert len(doc) >= 1


def test_arabic_scan_has_no_selectable_text():
    with fitz.open(ROOT / 'samples' / 'synthetic_invoice_ar_scanned.pdf') as doc:
        assert not doc[0].get_text('text').strip()


def test_en_pdf_has_actual_text():
    with fitz.open(ROOT / 'samples' / 'synthetic_invoice_en.pdf') as doc:
        assert 'INV-2026-0042' in doc[0].get_text('text')


def test_score_detects_missing_value():
    r = evaluate('Invoice: INV-2026-0042 Total: 6400', {'id': 'INV-2026-0042', 'missing': 'Amina Test'})
    assert r['matched'] == 1
    assert not r['per_field']['missing']


def test_arabic_normalization():
    assert normalize('  ليلى  تجريبي ') == 'ليلى تجريبي'
