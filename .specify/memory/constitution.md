# MDIA Constitution

## Core Principles

### I. Evidence Before Extraction

Every extracted value MUST retain the exact printed value, source page, supporting
text, evidence identifier, provenance method, and available geometry. Estimated
PaddleOCR word boxes MUST be labeled as estimates, never independent proof.
Missing or ambiguous values MUST be marked unresolved for human review, not
inferred from totals, neighboring rows, medical context, or language models.

### II. Financial Non-Mutation

MDIA MUST NOT silently create, delete, recalculate, or alter a billed amount.
Arithmetic and row/column conflicts MUST produce explicit findings while
preserving original evidence and raw output. Corrections MUST be separate,
attributable human actions. MDIA MUST NOT authorize or deny claims automatically.

### III. Local-First Patient Privacy

Document processing MUST work locally after necessary model downloads. Patient
documents, OCR text, and derived records MUST NOT be sent to external services
without explicit, separately approved handling. Tests and issue/PR artifacts MUST
use synthetic or appropriately de-identified, consented data; no patient material
may be committed to Git or printed in CI logs.

### IV. Regression-Gated Accuracy

Changes to tables, OCR, evidence, or financial fields MUST have focused unit tests
and evaluation against a fixed, labeled, independent holdout. Reports MUST show
exact field accuracy, per-layout breakdown, missed true rows, extra false rows,
evidence grounding, and review/abstention rates. A change MUST NOT be described
as an accuracy improvement based on isolated unit tests or altered test labels.
Any loss of previously correct billed items MUST block promotion pending review.

### V. Conservative Incremental Delivery

Preserve the current Python API, Windows and Docker entry points, and the
MDIA/MCIAS project boundary. Develop on feature branches and treat open draft
experiments as unverified. A change MUST NOT merge to `main` before CI, the
relevant acceptance benchmark, and a human review of financial safety pass.
Favor small, reversible changes over new hosted systems or paid integrations.

## Operational Constraints

- Target use: Arabic/English scanned and text PDFs and medical invoice images.
- Existing baseline: 4,895/5,776 correct fields (84.75%) and 99 extra rows on
  300 synthetic invoices. This is a historical benchmark, NOT production accuracy.
- Human review is mandatory for unresolved, estimated, or inconsistent evidence.
- A literal 100% on arbitrary real-world scans cannot be guaranteed. The goal
  is zero unsupported automatically accepted values, with measured field recall,
  precision, and abstention on explicitly defined datasets.
- No unapproved paid OCR services, external PHI uploads, or automatic claim actions.

## Delivery and Acceptance Gates

1. Define a measurable specification and acceptance dataset before changing code.
2. Run existing regressions and record environment-caused skips separately from
   actual algorithmic failures.
3. Add a test that reproduces the defect; implement the smallest evidence-preserving
   correction and compare both true-positive and false-positive item counts.
4. Require all applicable CI checks and holdout comparisons to pass; investigate
   any correctness regression instead of weakening assertions.
5. Publish a transparent READY/BLOCKED report. Only a verified human-reviewed
   release can be marked READY for pilot use; no implicit financial automation.

## Governance

This constitution governs MDIA specifications, plans, tasks, code reviews, and
acceptance. Amendments require a documented rationale and owner approval;
MAJOR versions remove/redefine guarantees, MINOR versions add principles or
material rules, and PATCH versions clarify wording. Every pull request MUST
verify affected principles and record evidence of the corresponding gates.

**Version**: 1.0.0 | **Ratified**: 2026-10-28 | **Last Amended**: 2026-10-28
