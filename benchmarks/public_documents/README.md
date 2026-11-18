# Public real-document evidence plan (2026-11-19)

This directory describes **public third-party research datasets**, not real supplier PO/GRN/invoice triplets. NEVER call these financial approval ground truth.

## Verified dataset catalog

| Dataset | Evidence and labels | Rights/access | What it can test |
| --- | --- | --- | --- |
| [SROIE](https://huggingface.co/datasets/jsdnrs/ICDAR2019-SROIE) | 987 scanned receipts, annotated totals, company, date, address, text boxes | CC BY 4.0; attribution required | OCR text fidelity and receipt field extraction, not invoice-to-PO/GRN matching |
| [Zenodo 6371710](https://zenodo.org/records/6371710) | 813 real Portuguese invoice/receipt images; seller, dates, amounts and tax labels | Need explicit license and privacy review before ingestion or redistribution | Invoice field extraction and multilingual layouts |
| [DocILE](https://docile.rossum.ai/) | 6,680 annotated business documents plus synthetic and unlabeled data; line-item labels | Access request required, research terms | Invoice line-item extraction under applicable permission |
| [Salesforce INV-CDIP](https://github.com/salesforce/inv-cdip) | 350 labeled invoices, 7 header fields | CC BY-NC 4.0 + original-document terms | Noncommercial invoice field benchmarks |

Sources are registered with machine-readable metadata in `sources.json`; no third-party images are committed to this repo.

## First reproducible HOLDOUT experiment

`python -m benchmarks.public_documents.sroie_benchmark --limit 10 --out results/sroie-10.json`

- Reads the public Hugging Face dataset server `test` split only; **fails** rather than substituting training rows.
- Downloads only 10 test image records into memory and checks SHA-256 of their exact bytes.
- Uses Tesseract English OCR, records whether each *annotated total string occurs* in raw OCR output and the image fingerprint; saves only aggregate/numeric metrics and row ids.
- **DOES NOT** measure invoice field localization, structured extraction accuracy, three-way matching, physical receipt, issuer authentication or invoice validity.
- Fails (no fake passing report) if network access, annotated totals, split or images are missing.
- Research workflow: `.github/workflows/public-document-benchmark.yml` (pull request or manual run), uploads a small JSON report only.
- For fair engine comparison later, keep a fixed image/hash manifest and compare Tesseract, PaddleOCR, DeepSeek-OCR, and MDIA field extraction on the same rows without changing ground truth.
- Do not claim accuracy 100% or zero silent financial errors from these receipts.

## What is STILL required before full financial acceptance

Public receipt images and invoice label datasets **do not normally contain matching authentic purchase orders and warehouse receipts for the same transaction**. Never synthesize a PO/GRN and call it independent real ground truth. Such datasets test OCR and extraction only. For 3-way verification, collect openly licensed multi-document business procurement records with independently matched linkage/receipts and independent human auditing; if unavailable, use synthetic cases only and label them honestly.

The benchmark may expose company or purchaser identifiers embedded in public receipts. Treat source bytes as untrusted, ephemeral test fixtures, avoid uploading image bytes or raw OCR text to GitHub, and comply with source licenses. Any production or training use requires legal review and applicable access rights.
