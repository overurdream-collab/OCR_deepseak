# DeepSeek-OCR 2 — synthetic medical PDF pilot

Independent experiment to measure OCR text coverage on synthetic hospital invoices, prescriptions and clinical reports. **Not yet a complete medical document extraction product.**

- CPU baseline: PyMuPDF for text PDFs and Tesseract (English + Arabic) for scanned PDFs.
- Model option: official deepseek-ai/DeepSeek-OCR-2 via Transformers; explicit NVIDIA CUDA requirement.
- **Never claim CPU baseline numbers are DeepSeek-OCR 2 performance.**
- Four synthetic PDFs are generated from source code; no patient records or production credentials are used.

## Baseline commands

Install Python dependencies and Tesseract OCR with the Arabic language pack (and a DejaVu Sans font). Then:

~~~bash
python -m pip install -r requirements-cpu.txt
python scripts/create_synthetic_pdfs.py
PYTHONPATH=. python -m src.pilot --engine hybrid --samples samples --output results/hybrid.json
PYTHONPATH=. python -m pytest -q
~~~

## GPU DeepSeek-OCR 2 evaluation

Inspect upstream sources, remote-code execution, license, and the official GPU environment requirements before installing model dependencies:

- https://github.com/deepseek-ai/DeepSeek-OCR-2
- https://huggingface.co/deepseek-ai/DeepSeek-OCR-2

The official model card describes Python 3.12.9, CUDA 11.8, torch 2.6.0, transformers 4.46.3, flash-attn 2.7.3 and other dependencies. The script uses trust_remote_code=True, so review the exact model revision before running.

~~~bash
python scripts/create_synthetic_pdfs.py
PYTHONPATH=. python -m src.pilot --engine deepseek-ocr2 --samples samples --output results/deepseek-ocr2.json
~~~

This mode **fails if CUDA is absent**. It never silently switches to another OCR engine. The model weights are not included.

## Results / limitations

On a local CPU environment, six unit tests passed and the baseline raw substring checks matched 17/18 expected values (6/6 invoice EN, 4/4 prescription, 4/4 report, 3/4 invoice AR scan).

This is raw string coverage, NOT field-level accuracy, NOT accurate medication/diagnosis parsing, and NOT reliable price-to-item pairing. Arabic OCR missed a patient name and misread one price. Model-specific inference **has not run** without a GPU. See results/experiment-report.md.

No paid services, deployments, merged branches or real medical records are involved.

## Licensing

DeepSeek-OCR 2 declares Apache-2.0. Original pilot glue code is MIT licensed; verify individual dependency licenses independently.
