# Tasks: Arabic Invoice Table Acceptance Gates

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contract](contracts/acceptance-report.md)

**Tests**: Required by FR-008 and Constitution IV; all relevant changes must be tested before promotion.

**Organization**: MVP US1 first; US2 and US3 are subsequent independently verifiable extraction improvements.

## Phase 1: Setup

**Purpose**: Adopt Spec Kit without changing existing runtime behavior.

- [x] T001 Verify `.specify/memory/constitution.md` and `specs/001-arabic-invoice-acceptance/spec.md` protect local-only OCR, evidence, and financial non-mutation (FR-007, FR-009).
- [x] T002 Fix and cross-check the published per-layout baseline in `specs/001-arabic-invoice-acceptance/research.md` against `docs/MDIA_300_FIELD_FAILURE_ANALYSIS_AR.md` (FR-002).

## Phase 2: Foundational

**Purpose**: Ensure the quality gate reads actual existing benchmark fields.

- [x] T003 Verify `scripts/benchmark_invoice300.py` score schema and freeze only source-verified correctness flags (no medical text) from run `40180808910` using `scripts/freeze_invoice300_baseline.py` into `scripts/baselines/invoice300_paddle_v1.json` (FR-001, FR-002, FR-004).

**Checkpoint**: Fixed historical baseline and score contract agreed before implementation.

## Phase 3: User Story 1 — Compare Proposed Release (Priority: P1) 🎯 MVP

**Goal**: A single command rejects incomplete or numerically degraded 300-case results.

**Independent Test**: Fabricated report fixtures derived from the fixed case identity set are accepted only at or above each baseline; invalid/partial reports fail closed.

### Tests for User Story 1

- [x] T004 [US1] Write failing PASS/BLOCKED contract tests for all 300 case IDs, duplicate/missing shard, wrong seed, mismatched counters, historic correct-field loss concealed by offsetting gains, and extra rows in `tests/test_invoice300_acceptance.py` (FR-001, FR-002, FR-004, SC-001, SC-002).

### Implementation for User Story 1

- [x] T005 [US1] Implement strict validation, per-case correct-field and false-row preservation, per-layout baseline comparison, JSON decision, and nonzero BLOCKED exit status in `scripts/check_invoice300_acceptance.py` (FR-001, FR-002, FR-003, FR-004, SC-001, SC-003).
- [x] T006 [US1] Add a final aggregate acceptance job reading all six non-overwritten shard artifacts in `.github/workflows/mdia-release-300-acceptance.yml` (FR-003, FR-009).
- [x] T007 [US1] Run the isolated tests and demonstrate a PASS and intentional BLOCKED report; record commands in `specs/001-arabic-invoice-acceptance/quickstart.md` (SC-001, SC-002, SC-003).

**Checkpoint**: US1 is usable independently with no changes to `mdia/`.

## Phase 4: User Story 2 — Preserve Verified Services (Priority: P2)

**Goal**: Improve table row accuracy without dropping genuine billed items.

**Independent Test**: The stacked-header regression retains all three correct lines; summary rows are excluded precisely, and benchmark accuracy does not decline in any layout.

### Tests for User Story 2

- [x] T008a [US2] Reproduce OCR-split Arabic service/numeric lines and test both vertical orders, source evidence, human review, neighboring-row isolation, summary labels, overlapping geometry and ambiguous extra numbers in `tests/test_arabic_unheaded_fragments.py`.
- [ ] T008 [US2] Add tests for multi-token signed amounts, Arabic/English summary rows and actual services in `tests/test_invoice_table_precision.py` (FR-005, FR-006, FR-008, SC-004).

### Implementation for User Story 2

- [x] T009a [US2] Recover disjoint, adjacent OCR fragments in `unheaded_arabic_invoice_rows` using observed tokens only; preserve both source line IDs and mandatory review. Full 300-case real Paddle verification passed with **no regression and no accuracy delta** (GitHub run `40751589356`).
- [x] T009b [US2] Normalize only Paddle OCR text-value Persian `ک/ی` lookalikes to Arabic `ك/ي`, while keeping `raw` and evidence unchanged and mandating review; reproduce `ar_mixed_18` improvement from 15/27 to 19/27 fields on real local Paddle inference. Full 300-case gate passed with 218 additional correct fields (GitHub run `40753884964`).
- [x] T009c [US2] Audit 21 synthetic PDFs through real PaddleOCR for other Persian/Urdu extended script characters; implement review-only detection (no replacement) for non-equivalent extended letters with focused negative tests. Record official-model alternatives and licensing in `research.md`.
- [x] T009d [US2] Guard against conflating `ي` and `ى`: preserve ambiguous final/isolated Farsi `ی`, flag human review, and test clinically meaningful `كلى`/`كلي` distinction. Unicode source and decision documented in `research.md`.
- [ ] T009 [US2] Refine `mdia/tables.py` only after the focused tests fail on an actual defect; keep suspect rows for review and do not invent monetary values (FR-005, FR-006).
- [ ] T010 [US2] Run the six-shard real PaddleOCR benchmark with `scripts/benchmark_invoice300.py` and compare using `scripts/check_invoice300_acceptance.py` before proposing a merge (FR-002, SC-004).
- [x] T010a [US2] Test official Tesseract `tessdata_best` Arabic/English on all 300 synthetic PDFs alongside the unchanged PaddleOCR model; publish exact per-layout and per-field gains/losses with source hashes, explicit non-promotion decision and independent comparison tests. See `docs/MDIA_OCR_ENGINE_COMPARISON_2026-10-28.md`.

**Checkpoint**: No legitimate service regression and no worsened per-layout scores; otherwise BLOCKED.

## Phase 5: User Story 3 — Review Financial Uncertainty (Priority: P3)

**Goal**: Human reviewers see provenance limitations without automatic financial edits.

**Independent Test**: Corrupt/missing numeric cases show original source and review flags.

### Tests for User Story 3

- [ ] T011 [US3] Add provenance/estimated-geometry and no-auto-correction cases to `tests/test_invoice_field_evidence.py` (FR-007, SC-005).

### Implementation for User Story 3

- [ ] T012 [US3] Repair only proved gaps in `mdia/invoice_reconciliation.py` or `mdia/pipeline.py`, retaining original values and review warnings (FR-007).

**Checkpoint**: No unsupported accepted financial field in targeted negative cases.

## Phase 6: Polish & Release Evidence

- [ ] T013 Recheck synthetic results and document real-patient validation as BLOCKED until authorized, consented and de-identified data are available in `docs/MDIA_RELEASE_ACCEPTANCE_AR.md` (SC-006).
- [ ] T014 Run full available unit tests and review GitHub CI logs for candidate branch; keep `main` unchanged until owner approval and actual benchmark evidence (FR-008, FR-009).

## Dependencies & Execution Order

- Phase 1 → Phase 2 → Phase 3 (US1 gate) first.
- US2 and US3 depend on the setup but are independently testable; US2's benchmark must use US1's acceptance tool.
- Phase 6 waits for the relevant user story's full evidence, not a green isolated unit test.
- Tasks touching `mdia/tables.py` or `tests/` that share behavior are sequential to avoid conflicting interpretation.

## Parallel Opportunities

- None required for the MVP; T004 tests precede T005 implementation (test-first), then T006 workflow integration.
- Future US2 sample analysis and US3 provenance audit can be investigated independently if staffing becomes available.

## Implementation Strategy

1. Deliver P1 quality-gate tooling independently, leaving the extraction algorithm unchanged.
2. Validate the gate using complete synthetic score fixtures, then arrange the 300-run acceptance when compute is available.
3. Only then repair row/column association, with test-first edits and no degradation to correct services.
4. Consider real-document trials only with separately approved privacy-safe samples; do not promise universal 100% OCR.
