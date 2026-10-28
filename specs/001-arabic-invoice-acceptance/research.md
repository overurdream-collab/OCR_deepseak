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
