#!/usr/bin/env python3
"""Build synthetic English and Arabic medical PDFs; no personal or patient data."""
import json
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / 'samples'
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'


def en_pdf(path, title, lines):
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    c.setFont('Helvetica-Bold', 18)
    c.drawString(45, h - 55, title)
    c.setFont('Helvetica', 12)
    y = h - 92
    for line in lines:
        c.drawString(48, y, line)
        y -= 24
    c.setFont('Helvetica-Oblique', 8)
    c.drawString(45, 34, 'SYNTHETIC TEST DOCUMENT - NOT A REAL MEDICAL RECORD')
    c.save()


def arabic_scanned_pdf(path):
    im = Image.new('RGB', (1600, 2200), 'white')
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype(FONT, 44)
    headline = ImageFont.truetype(FONT, 62)
    left = 125
    d.text((1450, 160), 'فاتورة طبية اصطناعية', font=headline, fill='black', anchor='ra', direction='rtl')
    arabic_rows = [
        'اسم المريض: ليلى تجريبي',
        'الخدمة     الكمية     سعر الوحدة     الإجمالي',
        'استشارة طبية        1        2000        2000',
        'تحليل دم           1        1500        1500',
        'الإجمالي: 3500',
    ]
    ys = [360, 650, 760, 870, 1030]
    for y, row in zip(ys, arabic_rows):
        d.text((1450, y), row, font=font, fill='black', anchor='ra', direction='rtl')
    d.text((left, 475), 'INV-AR-2026-007', font=font, fill='black')
    d.text((left, 555), '2026-10-23', font=font, fill='black')
    d.text((left, 1950), 'SYNTHETIC TEST ONLY', font=font, fill='black')
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    image_bytes = __import__('io').BytesIO()
    im.save(image_bytes, format='JPEG', quality=92, optimize=True)
    page.insert_image(page.rect, stream=image_bytes.getvalue())
    doc.save(str(path))
    doc.close()


def main():
    SAMPLES.mkdir(parents=True, exist_ok=True)
    en_pdf(SAMPLES / 'synthetic_invoice_en.pdf', 'SYNTHETIC HOSPITAL INVOICE', [
        'Invoice: INV-2026-0042',
        'Patient: Amina Test',
        'Provider: Example Medical Center',
        'Service Date: 2026-10-23',
        'Item | Quantity | Unit Price | Line Total (YER)',
        'Consultation | 1 | 2500 | 2500',
        'CBC Lab Test | 1 | 1500 | 1500',
        'Amoxicillin 500 mg Capsules | 2 | 1200 | 2400',
        'TOTAL YER: 6400',
    ])
    en_pdf(SAMPLES / 'synthetic_prescription_en.pdf', 'SYNTHETIC PRESCRIPTION', [
        'Patient: Amina Test',
        'Date: 2026-10-23',
        'Medication: Amoxicillin 500 mg Capsules',
        'Dose: 1 capsule twice daily for 5 days',
        'Prescriber: Dr Example',
    ])
    en_pdf(SAMPLES / 'synthetic_clinical_report_en.pdf', 'SYNTHETIC CLINICAL REPORT', [
        'Patient: Amina Test',
        'Date: 2026-10-23',
        'Suspected diagnosis: Acute pharyngitis',
        'Hemoglobin: 12.4 g/dL',
        'WBC: 7.2 x10^9/L',
        'Clinical note: Synthetic data for OCR testing only.',
    ])
    arabic_scanned_pdf(SAMPLES / 'synthetic_invoice_ar_scanned.pdf')
    truth = {
        'synthetic_invoice_en.pdf': {
            'invoice_id': 'INV-2026-0042', 'patient': 'Amina Test',
            'service': 'CBC Lab Test', 'medication': 'Amoxicillin 500 mg',
            'total_yer': '6400', 'line_price_1': '2500',
        },
        'synthetic_prescription_en.pdf': {
            'patient': 'Amina Test', 'medication': 'Amoxicillin 500 mg',
            'dose': 'twice daily', 'duration': '5 days',
        },
        'synthetic_clinical_report_en.pdf': {
            'patient': 'Amina Test', 'diagnosis': 'Acute pharyngitis',
            'hemoglobin': '12.4', 'wbc': '7.2',
        },
        'synthetic_invoice_ar_scanned.pdf': {
            'invoice_id': 'INV-AR-2026-007', 'patient': 'ليلى تجريبي',
            'total_yer': '3500', 'service': 'استشارة طبية',
        }
    }
    (SAMPLES / 'ground_truth.json').write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Generated 4 synthetic PDFs in', SAMPLES)


if __name__ == '__main__':
    main()
