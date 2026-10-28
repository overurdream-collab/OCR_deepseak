# Data Model: 300-Invoice Release Gate

## Benchmark Case

- `case`: unique identifier, one of 300 exact IDs from `all_cases()`; non-empty string.
- `layout`: one of six published layouts.
- `model`: exactly `paddle_arabic` for the first release gate.
- `matched`, `total`, `with_evidence`: nonnegative integers with `0 <= with_evidence <= matched <= total`.
- `expected_item_rows`, `matched_item_names`, `extracted_item_rows`, `extra_item_rows`: nonnegative integers; `matched_item_names <= expected_item_rows`; `extra_item_rows == max(0, extracted_item_rows - matched_item_names)`.
- `real_paddle_detected`: `true` for every report case.
- `runtime_error`, `page_failures`: absent/empty in PASS cases.
- `checks`: one entry per expected field, with booleans `matched` and `linked_evidence`, allowing source-score consistency validation.

## Partition Report

- `status`: exactly `completed_real_ocr`.
- `seed`: exactly `20261026`.
- `version`: exactly `SYNTHETIC-INVOICE-300-HOLDOUT-v1`.
- `shard`: distinct integer `0..5`; `shards`: `6`; `cases`: `50`.
- `engines`: contains exactly `paddle_arabic`.
- `results`: exactly 50 Benchmark Cases; set is disjoint across shards.
- `summary.paddle_arabic`: figures consistent with the detail rows.

## Acceptance Decision

- `status`: `PASS` or `BLOCKED`.
- `dataset`: seed, version, engine, expected and observed document counts.
- `totals`: `matched`, `expected`, `accuracy_percent`, `extra_item_rows`, `failures`.
- `by_layout`: six records containing case count, counts, baseline, and delta.
- `reasons`: specific strings identifying missing/invalid data or a layout regression.
- A blocked decision MUST carry at least one reason and the command MUST exit nonzero.

## Frozen Historic Case Baseline

- One source-verified, compact correctness bitstring per exact case ID, in the benchmark's field-check order: `1` = historically correct, `0` = historically incorrect.
- One nonnegative historic `extra_item_rows` count per case.
- A candidate MUST NOT change any historical `1` to an incorrect field or increase the historical case's false-row count; gains elsewhere cannot offset these losses.
- Source: GitHub Actions run `40180808910`, synthetic only. No OCR text, patient name, or monetary content is retained.

## Relationships and State

Six Partition Reports -> 300 unique Benchmark Cases -> one Acceptance Decision.
`PASS` requires completeness first, numerical checks second; any violation results in `BLOCKED`.
