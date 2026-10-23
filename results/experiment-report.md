# Synthetic medical PDF experiment — verified local CPU results

## What was executed
- Four generated synthetic PDF fixtures: English invoice, prescription, clinical report, and Arabic scanned invoice.
- CPU baseline: PyMuPDF for selectable text and Tesseract eng+ara for scanned pages.
- Six pytest tests passed in a local environment on 2026-10-24.
- Actual DeepSeek-OCR 2 inference **not executed**: NVIDIA CUDA GPU unavailable.

## Raw expected-substring checks only

| PDF | Matches |
|---|---:|
| English invoice | 6/6 |
| English prescription | 4/4 |
| English clinical report | 4/4 |
| Arabic scanned invoice | 3/4 |
| Total | 17/18 |

The Arabic scanned patient name was missed; one price was OCR-read inaccurately. This is **not** extraction accuracy and does not prove correct price-to-item pairing. It does not validate medical coding or diagnosis extraction. The model harness matches the upstream documented Transformers interface, but requires a separate CUDA runtime to verify live DeepSeek-OCR 2 output.

## Next verification
Run model mode on CUDA-capable test hardware, compare against the same synthetic fixtures and evaluate rows, quantities, prices and clinical entities separately. Do not use real medical data for the pilot.

## GitHub scope
Branch-only experiment; do not merge into main or deploy. Synthetic fixture PDFs regenerate from scripts/create_synthetic_pdfs.py.
