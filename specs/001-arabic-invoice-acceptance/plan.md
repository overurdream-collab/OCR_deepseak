# Implementation Plan: Arabic Invoice Table Acceptance Gates

**Branch**: `feat/mdia-spec-kit-acceptance` | **Date**: 2026-10-28 | **Spec**: [spec.md](spec.md)

**Input**: Fixed-baseline release quality gate followed by conservative table-extraction improvements; no real-patient deployment or automatic financial authorization.

## Summary

Add an independent, deterministic evaluator over six real PaddleOCR benchmark outputs. Require exact 300-case coverage, stable seed/version, per-layout non-regression AND per-field/per-case preservation against the frozen 2026-10-25 GitHub run, and a clear machine-/human-readable PASS or BLOCKED result. Wire it into the existing manual 300-PDF acceptance workflow after all shard artifacts arrive. Preserve table and financial source semantics. Future parser changes use the same gate and the existing stacked-header regression rather than suppressing suspected OCR rows without evidence.

## Technical Context

**Language/Version**: Python 3.11–3.12; current CI Python 3.12

**Primary Dependencies**: Python standard library for checker; existing `pypdfium2`, `pdfplumber`, `PaddleOCR` (CI), Tesseract, `reportlab` for runtime/test generation

**Storage**: JSON benchmark artifacts; local-only job store, no new database

**Testing**: Python `unittest`, fixture-derived synthetic reports; separate 300 real PaddleOCR inference jobs on GitHub Actions

**Target Platform**: Windows 11/local Docker and Linux CI; no new SaaS OCR

**Project Type**: Existing local Python OCR + HTTP app with evaluation scripts

**Performance Goals**: Aggregate 300 already-produced reports in fewer than 5 seconds

**Constraints**: No OCR rerun inside comparator; zero clinical data; no false PASS; no modification of source amounts or mainline behavior by report tooling

**Scale/Scope**: Six shards, 50 cases each, six known layouts, one OCR engine; later production-like holdouts are separate

## Constitution Check

**Gate before research — PASS**:

- Evidence: comparator reads existing truth-linked scores; no newly asserted field geometry.
- Financial integrity: no amount is inferred or edited; only benchmark counts are evaluated.
- Privacy: inputs are synthetic and local JSON; no PHI uploaded.
- Accuracy: existing 4,895/5,776 and 99 false-row baseline is enforced per layout AND at the historical correct-field/false-row level for each synthetic case.
- Delivery: feature branch, existing `unittest`, manual 300-PDF workflow, no new paid vendor.

**Gate after design — PASS**: Contract rejects invalid reports and avoids comparison across different dataset seeds/versions. A passing synthetic benchmark is explicitly not production certification.

## Project Structure

### Documentation (this feature)

```text
specs/001-arabic-invoice-acceptance/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/acceptance-report.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
mdia/
├── tables.py                    # future targeted row-preservation change
├── invoice_reconciliation.py    # existing review-only evidence gate
└── pipeline.py                  # existing extraction and provenance
scripts/
├── benchmark_invoice300.py      # existing case records and score schema
├── check_invoice300_acceptance.py # new acceptance aggregator
├── freeze_invoice300_baseline.py  # audited one-time manifest generator
└── baselines/invoice300_paddle_v1.json # synthetic correctness flags only
tests/
├── test_hard.py                 # existing stacked-header regression
└── test_invoice300_acceptance.py # new fast fail-closed contract tests
.github/workflows/
└── mdia-release-300-acceptance.yml # manual shard runs + final summary job
```

**Structure Decision**: Keep the current Python layout. The evaluator is a pure standard-library script independent of the OCR engine; existing API and extractor remain unchanged in the first implementation increment.

## Complexity Tracking

None. No constitution exceptions or new framework.
