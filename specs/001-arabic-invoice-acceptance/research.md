# Research: Arabic Invoice Acceptance

## Decision 1 — Reuse the existing frozen synthetic benchmark

- **Decision**: The first gate consumes `scripts/benchmark_invoice300.py` `results.json` from each of six shards and verifies dataset seed `20261026` and version `SYNTHETIC-INVOICE-300-HOLDOUT-v1`.
- **Rationale**: This is the benchmark behind the published 4,895/5,776 result; new data or scoring semantics would make comparisons invalid.
- **Alternatives considered**: A new, smaller sample would be faster but would not support comparison with 2026-10-25 results.

## Decision 2 — Audited per-case flags as well as a per-layout baseline

- **Decision**: Freeze correct/expected fields per layout from `docs/MDIA_300_FIELD_FAILURE_ANALYSIS_AR.md`: `en_standard=910/942`, `en_reordered=927/970`, `en_compact=921/958`, `ar_shaped=758/1018`, `ar_visual=710/930`, `ar_mixed=669/958`; extra-row upper bounds `3,5,4,30,20,37` respectively. Pin the correct-field masks and extra rows of all 300 synthetic cases from the original complete GitHub Actions run `40180808910` (commit `5977a980474f173f1cfbcea4b2e85a8f515cee5a`) in `scripts/baselines/invoice300_paddle_v1.json`.
- **Rationale**: A gain in English cannot hide a loss in Arabic mixed; even a gain in one field of the same case must not hide the loss of another historically correct field. The compact manifest contains correctness bits, not OCR text or patient data.
- **Alternatives considered**: Overall or per-layout aggregate only (can conceal offsetting regressions). The original six artifact archives were fetched from the official recorded run to make the stronger comparison possible.

## Decision 3 — Complete source validation before scoring

- **Decision**: Require six distinct shard IDs `0..5`, 50 cases each, 300 unique exact case IDs generated from the existing deterministic `all_cases()` source, matched check counters, and no runtime errors. Reject reports with wrong model, missing status, or mismatched per-row vs summary counts.
- **Rationale**: Incomplete or fabricated metrics can otherwise produce false PASS.
- **Alternatives considered**: Trust each shard summary alone (not sufficient to detect duplicate or omitted invoices).

## Decision 4 — No ambiguous geometry-based deletion without evaluation

- **Decision**: Reject PR #13 as a release candidate until its known `test_h2_two_line_header_stacked_labels_negative_amounts` regression is fixed and all 300 benchmark gates pass. Do not merge the PR or reinterpret its single-line unit tests as a benchmark win.
- **Rationale**: CI run `40597637455` showed two valid service rows suppressed by its geometry gate.
- **Alternatives considered**: Promote the rule now to reduce extra false rows (could lose medically and financially valid charges).

## Decision 5 — Synthetic acceptance vs real-world calibration

- **Decision**: Publish distinct synthetic PASS/BLOCKED and real-document readiness status. Real patient data requires owner consent, de-identification, secure local test infrastructure, and human audit before production claims.
- **Rationale**: 84.75% synthetic accuracy is not clinical accuracy; 100% on unknown scans cannot be guaranteed.
- **Alternatives considered**: Infer deployment confidence from synthetic tests (unsafe).

## Decision 6 — Distinguish Unicode script confusion from OCR misrecognition

- **Evidence**: Real PaddleOCR on synthetic `ar_mixed_18` returned the service name `تحلیل سکر صائم` using Persian yeh (`U+06CC`) and keheh (`U+06A9`), instead of Arabic `ي` and `ك`. Without changing amounts, canonicalizing only the OCR *text value* increased that case's exact score from 15/27 to 19/27. The six-shard real Paddle evaluation **passed** at 5,113/5,776 (88.52%) vs 4,895/5,776 (84.75%) previously. The `ar_shaped` layout gained 97 correct fields and `ar_mixed` 121; no previously correct field was lost. Extra rows reported by the scorer decreased from 99 to 38 because more true service names matched; this does **not** prove 61 physical rows were deleted. GitHub Actions run `40753884964`.
- **Decision**: Keep `field.raw` and provenance unchanged, expose a reviewable canonical Arabic `value` **only** for the verified `ک/ی → ك/ي` OCR text variants, never for financial values. Any other extended Arabic-script letter (e.g. Urdu `پ چ ژ گ ں ہ ھ ۃ ے`) must be kept exactly as OCR saw it and flagged for human review, not silently transliterated.
- **Diagnostic**: A local 21-PDF real-Paddle audit across `ar_shaped`, `ar_visual` and `ar_mixed` detected only 16 `U+06A9` and 8 `U+06CC` nonstandard Arabic-script letters; no further extended letters occurred in **those samples**. This limited negative result cannot exclude variants in unknown real-world invoices.
- **Rationale**: Unicode Arabic, Persian and Urdu share script and similar glyph shapes, but distinct letters are not always semantically interchangeable. Medical names and amounts must retain auditable source text.
- **Alternatives considered**: Replace every Persian/Urdu lookalike (may corrupt genuine names), or retrain the entire recognition model immediately (unnecessary before testing existing models and error patterns).

## Decision 7 — Benchmark ready-made Arabic OCR / table models before retraining

| Candidate | Verified capabilities | MDIA trial conditions |
| --- | --- | --- |
| [PaddleOCR-VL-1.6](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html) | Full document pipeline recognizes text and tables, including Arabic-family languages; official docs describe x64 CPU installation. | **First new candidate**: run the *complete* layout + VLM pipeline on frozen 300 cases, measure CPU speed and source evidence. Do not compare its general OmniDocBench score directly to MDIA field accuracy. |
| [EasyOCR](https://github.com/JaidedAI/EasyOCR) | Readily available multilingual recognition with an Arabic-script group supporting Arabic, Persian, Urdu and Uyghur. | **Second candidate**: run as an independent OCR backend on the same exact benchmark; preserve original boxes and confidence. |
| [Tesseract tessdata_best Arabic](https://github.com/tesseract-ocr/tessdata_best) | Open-source Arabic LSTM traineddata. | Low-cost second opinion for uncertain text/numbers, but disagreement must only flag review, never replace a monetary value. |
| [Surya](https://github.com/datalab-to/surya) | Layout, reading order and table recognition in 90+ languages; CPU via llama.cpp or GPU via vLLM. | Later trial; verify **model-weight commercial license terms** first, since Apache-2.0 code license alone does not cover commercial weight usage. |

- **Decision**: Keep the proven PaddleOCR baseline as the default. Test challenger engines in isolation on the **same 300 PDFs**, scoring exact fields and matched names, per-case false rows, source geometry, manual-review protections, CPU memory/speed, and licensing. Only promote a candidate after a passed regression gate and independently validated provenance. Do not claim 100% from a vendor's unrelated benchmark.
- **Rationale**: The initial 218-field gain came from a small text-normalization bug, not missing alphabet knowledge. Existing models trained across scripts and table layouts may address the remaining structural failures more cheaply than training from zero.
