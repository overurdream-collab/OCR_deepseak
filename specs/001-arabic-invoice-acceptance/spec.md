# Feature Specification: Arabic Invoice Table Acceptance Gates

**Feature Branch**: `feat/mdia-spec-kit-acceptance`

**Created**: 2026-10-28

**Status**: Draft — first incremental feature, not a claim of production readiness

**Input**: Improve MDIA's Arabic/English medical invoice extraction toward verified accuracy, starting by preventing unmeasured regressions, retaining correct invoice lines, and requiring human review for ambiguous amounts. The user requests an eventual 100% reading target.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compare a Proposed Release With the Baseline (Priority: P1)

As the MDIA owner, I want a clear acceptance report over the established 300 synthetic invoices before a change is called an improvement, so an apparent fix cannot silently lose valid charges or add invented rows.

**Why this priority**: PR #13 passed its new local unit cases but failed an existing invoice regression, dropping two correct services. The current six-way benchmark reports outcomes but does not enforce the previously published field/extra-row thresholds as a combined release gate.

**Independent Test**: Supply complete labeled score reports from all six partitions of the fixed dataset to the acceptance reviewer; it accepts an unchanged baseline and rejects missing, duplicated, incomplete, or degraded partitions.

**Acceptance Scenarios**:

1. **Given** six complete reports with exactly 300 distinct synthetic invoices and at least baseline field matches per layout and no more extra rows per layout, **when** release quality is evaluated, **then** a clear PASS report shows the exact counts and baseline differences.
2. **Given** a change with fewer correct fields or more extra rows in any layout, **when** evaluated, **then** the release is BLOCKED with layout-level reasons and no false claim of improvement.
3. **Given** a missing partition, duplicate invoice, failed OCR, unknown dataset, or inconsistent totals, **when** evaluated, **then** the report is BLOCKED rather than silently counting fewer samples.

---

### User Story 2 - Preserve Verified Services During Table Improvements (Priority: P2)

As a medical invoice reviewer, I want genuine service rows to remain visible even where their numbers or geometry are ambiguous, so I can inspect the printed amounts without losing medical charges.

**Why this priority**: The PR #13 numerical-cell gate suppressed two legitimate rows in the stacked-header fixture. Suppression and high confidence are different decisions.

**Independent Test**: Run the existing stacked-header invoice regression and new focused synthetic Arabic/English row tests; all printed billable items remain in output, while uncertain fields receive review annotations and are not automatically approved.

**Acceptance Scenarios**:

1. **Given** a legitimate service with multiple OCR tokens for a numeric cell, **when** parsed, **then** it is not silently deleted solely for that reason, and its evidence limitations trigger review.
2. **Given** a recognized subtotal, discount, VAT, or grand-total summary line, **when** reading billed items, **then** it does not become a billable service; an actual service containing a word like “Total” is not removed by keyword alone.

---

### User Story 3 - Review Uncertain Financial Fields (Priority: P3)

As a human reviewer, I want source-linked, unchanged values and explicit uncertainty messages for low-quality Arabic invoice cells, so I can correct an item without the system inventing or adjusting a charge.

**Why this priority**: A zero-error automated financial decision is unsafe when some OCR evidence is estimated or missing.

**Independent Test**: Inspect a synthetic invoice with ambiguous, contradictory, and missing printed amounts and verify its review status, source references, and untouched raw values.

**Acceptance Scenarios**:

1. **Given** an unreadable or conflicting amount, **when** the document is processed, **then** the original OCR/source representation is preserved and the item is flagged for human review, not reconciled automatically.
2. **Given** an estimate-only word location, **when** evidence is displayed, **then** the reviewer is told it is not independently verified geometry.

---

### Edge Cases

- Two nearly identical service rows or repeated numbers must remain independently traceable to the correct row.
- Arabic-Indic digits, decimal/group separators, negative values, split headers, and mixed RTL/LTR labels must not create guessed amounts.
- A case that finishes OCR but yields missing fields still counts as a failure in the accuracy denominator.
- Partition reports may be in arbitrary file order; the result must be identical.
- Real patient documents are excluded from source control and automatic CI evidence uploads.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The release reviewer MUST validate the exact identity, completeness, and uniqueness of the 300-invoice synthetic evaluation set, across all six layouts.
- **FR-002**: The release reviewer MUST compare exact field-match counts and extra extracted invoice rows per layout AND compare every historically correct field/extra row count per synthetic case with the frozen official run; any lost correct field or added false row MUST block promotion even if other fields improve.
- **FR-003**: The release report MUST state matched/expected field counts, total and per-layout accuracy, extra row counts, runtime failures, and explicit PASS/BLOCKED reasons; a PASS does not mean real-world accuracy.
- **FR-004**: Incomplete, inconsistent, duplicated, failed, wrong-engine, or unrecognized evaluation reports MUST fail closed.
- **FR-005**: The table parser MUST preserve printed, legitimate billed services under numeric ambiguity, while marking unverified values for human review instead of silently discarding them.
- **FR-006**: Financial summary rows MUST NOT be misrepresented as services, but real medical services MUST NOT be removed based on a broad substring match.
- **FR-007**: Source references and original printed monetary values MUST remain unchanged; mathematical discrepancies and estimated geometry MUST create review warnings instead of automatic corrections.
- **FR-008**: Automated tests MUST cover the acceptance reviewer and the known stacked-header negative-amount regression before any proposed table change is promoted.
- **FR-009**: The acceptance result MUST be usable as a separate review gate without introducing paid APIs or requiring transfer of patient records.

### Key Entities *(include if feature involves data)*

- **Benchmark Case**: Identified by synthetic case ID, layout, representation, expected and matched fields, item rows, and any OCR failure.
- **Partition Report**: One of six independent result sets tied to a fixed seed, dataset version, engine, and partition identifier.
- **Acceptance Decision**: Aggregate and per-layout counters, baseline deltas, PASS/BLOCKED status, and reasons.
- **Invoice Item**: A printed medical service with its original fields and source evidence; not a financial summary line.
- **Review Finding**: Explicit uncertainty, mismatch, missing proof, or non-independent geometry associated with an item/field.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For the unchanged historical aggregate (4,895 of 5,776 exact fields and 99 extra rows), the reviewer gives PASS; one lost historically correct field or one new spurious row in any case produces BLOCKED even if other newly correct fields offset the aggregate.
- **SC-002**: All 300 distinct invoices from the six fixed layouts are accounted for in every PASS; zero failed or silently omitted documents are allowed.
- **SC-003**: A one-command evaluation produces a human-readable decision and machine-readable counts within 5 seconds after result reports are present.
- **SC-004**: The existing fixture with three valid lines, including a negative adjustment, remains three correctly extracted rows in every candidate promoted for field evaluation.
- **SC-005**: No reviewed uncertain financial value is auto-modified and every unsupported or estimated value in targeted synthetic negative cases remains marked for review.
- **SC-006**: On a future separately approved, de-identified real-world holdout, accuracy and abstention are reported independently of synthetic success before any production-ready claim.

## Assumptions

- Initial work addresses release quality gates and known table regressions on the existing application, not a new OCR model or web interface.
- The published historical exact-field layout totals are 910/942, 927/970, 921/958, 758/1018, 710/930, and 669/958, respectively; allowed extra rows are 3, 5, 4, 30, 20, and 37.
- Existing offline extraction, API, Docker, Windows, and human correction workflows remain in place.
- No consented real-patient benchmark is currently available in the repository; it is a separately approved prerequisite for clinical deployment claims.
- “100%” is treated as an aspirational goal for defined, independently measured data and zero unsupported automatically accepted values, not a guaranteed outcome on arbitrary scans.
