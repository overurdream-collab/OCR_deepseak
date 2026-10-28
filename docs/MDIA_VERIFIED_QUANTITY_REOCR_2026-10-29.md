# MDIA — Proven automated OCR quantity repair (not arithmetic guessing)

**Date:** 2026-10-29
**Branch:** `feat/mdia-verified-quantity-reocr`
**PR:** #21, stacked on #20; **Draft, not merged to `main`**.

## Issue and remedy

PaddleOCR occasionally misrecognizes a printed numeral **3** as Latin **M**, even when the source invoice row contains an intact service name, unit price and printed total. In PR #20, we recovered the row but left quantity `M` unreadable. The user requested resolving such obvious source-recognition errors instead of routinely escalating them to a human.

**This change corrects the quantity from OCR, not from arithmetic:**

1. Keep the Paddle `M` and its **original linked evidence**. Only target source-local OCR quantities with `raw=M`, `status=unreadable`, original Paddle page, bounded source coordinates, and two observed extracted amount fields on that same page.
2. Render that page from the original **local PDF** at the configured OCR DPI; crop the quantity's own location. No remote APIs or patient uploads.
3. Run **Tesseract** on the single-digit crop in original and contrast-enhanced pixel preparations, using an explicit digit whitelist and multiple segmentation modes. A candidate must be recognized in BOTH image preparations with confidence ≥0.65 and at least one ≥0.70. Strong conflicting digits (≥0.80) block adoption.
4. Independently check that the **digit Tesseract actually recognized** satisfies `digit × observed unit_price == observed printed line_total` with no stated line discount. Arithmetic **never** supplies a missing OCR number. A candidate cannot be invented when the OCR image is unreadable.
5. Only if all the above pass, replace the extracted numeric quantity with Tesseract's source-read digit, create a **new Tesseract word-level source-evidence entry** and link to the old Paddle `M` evidence; mark `verification=auto_verified`. The original OCR's `M` is kept in `original_ocr_raw` and `original_ocr_evidence_id`.
6. Fail closed with `unreadable` for low confidence, conflicting digit, missing/unstable coordinates, missing price/total, discounts, unavailable Tesseract, or non-Paddle OCR. No quantity/price/total inferred from another row.

**Important qualification:** Automated extraction verification does not constitute a financial approval, and machine OCR word locations are not human-confirmed ground truth. Downstream medical claims and financial decisions continue to need their separately defined checks.

## Actual measured outcome

Real local PaddleOCR + Tesseract (no cloud OCR) on **the exact 300 frozen synthetic PDFs**, six parallel shards, full strict comparison:

- [GitHub Actions run 40779714961](https://github.com/overurdream-collab/OCR_deepseak/actions/runs/40779714961) — **SUCCESS**, including the original frozen gate AND the *independent field-by-field non-regression comparison* against the previously verified PR #20 [run 40776907768](https://github.com/overurdream-collab/OCR_deepseak/actions/runs/40776907768).
- [Full MDIA CPU / Arabic PDF regression run 40779714729](https://github.com/overurdream-collab/OCR_deepseak/actions/runs/40779714729) — **SUCCESS**: 194 tests run, **193 PASS + 1 SKIP**.

| Metric | Before | After |
| --- | ---: | ---: |
| Correct fields / 5,776 | 5,285 | **5,324** |
| Exact synthetic accuracy | **91.50%** | **92.17%** |
| Correct additional quantities | — | **39** |
| Correct Arabic quantities gained | — | **14** |
| Correct English quantities gained | — | **25** |
| Previously correct fields lost | — | **0** |
| False extra item rows | 38 | **38 (unchanged)** |
| Cases with improvement | — | **29** |
| Fields not yet exact | 491 | **452** |

All 39 gains were individual `item.*.qty` fields; no original correct fields or source evidence links were lost, and no extra fake invoice rows appeared. Verified illustrative synthetic cases include `ar_shaped_18`, `ar_mixed_18`, `ar_visual_48`, and `en_reordered_59`. Independent pre-patch OCR trials demonstrated Tesseract reading the digit 3 directly from original PDF crops, with variable confidence; strong disagreement blocks repair.

## Limits / release decision

- Tests are **synthetic**, not a guarantee on real hospital invoices or all fonts/scans.
- This model-assisted auto-resolution is limited to *very specific single-glyph `M` errors*, not all OCR confusions. For other unresolved characters the existing review path remains mandatory.
- Need independent anonymized, permissioned real medical invoice set, plus review of field-location robustness and any remaining 452 mismatches.
- No change to `main`, no deployment, no use of real patient data or paid external tools. Production promotion still needs user authorization.
