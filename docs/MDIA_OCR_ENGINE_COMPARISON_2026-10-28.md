# MDIA — real Tesseract Best vs PaddleOCR on 300 synthetic medical invoices

**Date:** 2026-10-28 · **Status:** comparison complete; **no automatic OCR promotion**

All PDFs are deterministic and synthetic (`SYNTHETIC-INVOICE-300-HOLDOUT-v1`, seed `20261026`). No patient data, API OCR service, paid model, or invented invoice amount was involved. The same 300 PDFs (150 English, 150 Arabic) were processed through the existing MDIA extraction, table association and strict field scorer, independently for each engine. The 20-PDF pilot initially overstated Tesseract Best performance and **must not** be used for a release decision.

## Model provenance

| Engine | Source | SHA-256 / provenance |
| --- | --- | --- |
| PaddleOCR PP-OCRv5 Arabic mobile | Existing `mdia/paddle_arabic.py` | GitHub Actions 300-PDF run [`40759614991`](https://github.com/overurdream-collab/OCR_deepseak/actions/runs/40759614991), head `c4da3171` (feature source commit `67bebb9f`) |
| Tesseract 5.3.4, Arabic `tessdata_best` | [Official `tessdata_best/ara.traineddata`](https://github.com/tesseract-ocr/tessdata_best/blob/main/ara.traineddata) | `ab9d157d8e38ca00e7e39c7d5363a5239e053f5b0dbdb3167dde9d8124335896` |
| Tesseract 5.3.4, English `tessdata_best` | [Official `tessdata_best/eng.traineddata`](https://github.com/tesseract-ocr/tessdata_best/blob/main/eng.traineddata) | `8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba` |
| Tesseract previous local Arabic model | Existing Tesseract `ara.traineddata`, 1.4 MB, version `4.00.00alpha:ara:synth20170629` | Preliminary 20-PDF comparison only, not used as the 300-case candidate |

Tesseract's official [best-model repository](https://github.com/tesseract-ocr/tessdata_best) describes LSTM-only recognition and Apache-2.0 licensing. Use `--oem 1` (MDIA already does so). Model size alone is not an accuracy guarantee.

## Exact structured-field results

| Invoice layout | Fields | Paddle correct | Tesseract Best correct | Paddle extra rows | Tesseract extra rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| English standard | 942 | 910 | **919** | 3 | 5 |
| English reordered columns | 970 | 927 | **943** | 5 | 6 |
| English compact headers | 958 | 921 | **948** | 4 | **2** |
| Arabic shaped | 1,018 | **855** | 660 | **3** | 39 |
| Arabic visual-order | 930 | **710** | 350 | **20** | 70 |
| Arabic-English mixed | 958 | **790** | 559 | **3** | 38 |
| **All 300 PDFs** | **5,776** | **5,113 (88.52%)** | **4,379 (75.81%)** | **38** | **160** |

Across 150 English invoices, Tesseract Best improved the aggregate from 2,758 to 2,810 correct fields (+52); across 150 Arabic invoices, Paddle led 2,355 to 1,569. Replacing the English model wholesale **still loses 45 previously correct English fields** (35 are monetary/quantity-related) while gaining 97 other English fields. **Therefore a layout- or language-only switch fails safety non-regression**, despite better average English accuracy.

The combined **hypothetical oracle** (a fictional selector that already knows the expected answers) would yield 5,350/5,776 = 92.62%: Tesseract alone finds **237** correct fields missing from Paddle; Paddle alone finds **971** missing from Tesseract; **426** fields defeat both. This is **not a deployable ensemble score**. The 300-case Tesseract run also lacked the document-level `requires_human_review` marker in 142 cases (this does not imply fields were clinically verified).

**Independent hard-regression warning:** Running the full existing test suite with `tessdata_best` installed as the globally selected Tesseract data failed `test_h9_skewed_scan_is_deskewed_and_highlights_land_on_ink` because OCR read the printed invoice ID `H-778` as `1-778`. The unchanged standard local model passes this test. The complete **145-test** suite on the normal MDIA setup passed (**144 passed, 1 skipped**). This is direct evidence that the new model is a supplementary candidate, **not a safe drop-in global replacement**.

All "extra rows" counts are the evaluator's unmatched-extracted-row metric, **not** a claim that every unmatched row was physically a false medical charge. The previous 20-case pilot saw Tesseract Best 358/396 (90.40%), standard Tesseract 286/396 (72.22%), and Paddle 367/396 (92.68%); the full run supersedes it.

## Replication (Windows/Linux with Tesseract installed)

1. Download `ara.traineddata` and `eng.traineddata` from the official `tessdata_best` repository into a **separate** `tessdata_best` folder; check SHA-256 above.
2. Set `TESSDATA_PREFIX` to that folder. MDIA uses the model directory without modifying the bundled/system Tesseract model. Keep `MDIA_OCR_LANG=ara+eng`; its Tesseract path already specifies `--oem 1`.
3. Generate independent shard reports with `python -m scripts.benchmark_invoice300 --shard N --shards 6 --engines tesseract --output-dir results/tess_best_shardN` for `N=0..5`. Keep the existing six Paddle reports for the same seed/version.
4. Run `python -m scripts.compare_invoice300_engines --primary results/paddle_shard*/results.json --candidate results/tess_best_shard*/results.json --fail-on-regression`. This must **exit 1** for automatic promotion and show all paired gains/losses. Without the optional flag, a valid comparison exits 0 even when the candidate is blocked (it is a diagnostic report, not a release gate).

`--primary` and `--candidate` expect exactly six already-expanded paths in each set. The comparator rejects missing cases, invalid shards, mismatched expected field values, spoofed engine labels, corrupt arithmetic of summary counts and runtime/page failures. It performs no OCR and cannot modify source data.

## Decision / next experiment

1. **Keep PaddleOCR as the default** for Arabic and mixed medical invoices and the frozen 88.52% baseline; do not overwrite fields or silently choose amounts from Tesseract.
2. Prototype a **review-only** second-opinion path: run Tesseract Best on uncertain lines/fields, preserve its own source bounding boxes, and expose text/number disagreement with both original source links. A reviewer decides; none of the 237 potential gains are presumed correct without evidence.
3. Trial a stronger ready-made **Arabic document layout/table model** such as [PaddleOCR-VL](https://www.paddleocr.ai/main/en/version3.x/algorithm/PaddleOCR-VL/PaddleOCR-VL.html) on a fixed subset, recording exact fields, same-row arithmetic, true word/line box provenance, CPU resources and licensing. Promote only after a full independent 300-case non-regression run and de-identified real-invoice assessment.

**Bottom line:** Better Arabic OCR needs *table understanding plus verification*, not just a larger alphabet recognizer. A higher average score that silently erases a legitimate medical charge is not an acceptable improvement.
