# MDIA Constitution

## Core Principles

### I. Evidence Before Extraction

Every extracted value MUST retain the exact printed value, source page, supporting
text, evidence identifier, provenance method, and available geometry. Estimated
PaddleOCR word boxes MUST be labeled as estimates, never independent proof.
Missing or ambiguous values MUST NOT be accepted or inferred from totals,
neighboring rows, medical context, or language models. The product goal is
fully automatic extraction with no human referral AND no missing, false, or
invented fields; unresolved outputs fail the acceptance gate, rather than
counting as a successful zero-human outcome.

### II. Financial Non-Mutation

MDIA MUST NOT silently create, delete, recalculate, or alter a billed amount.
Arithmetic and row/column conflicts MUST produce explicit findings while
preserving original evidence and raw output. Corrections MUST be independently grounded in the source and recorded with
original OCR text plus independent verification evidence. No human-referral
shortcut or hidden error ledger qualifies as successful correction.
MDIA MUST NOT authorize or deny claims automatically.

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
evidence grounding, and error, missed-field, spurious-row, and human-referral rates. A change MUST NOT be described
as an accuracy improvement based on isolated unit tests or altered test labels.
Any loss of previously correct billed items MUST block promotion pending review.

### V. Conservative Incremental Delivery

Preserve the current Python API, Windows and Docker entry points, and the
MDIA/MCIAS project boundary. Develop on feature branches and treat open draft
experiments as unverified. A change MUST NOT merge to `main` before CI, the
relevant acceptance benchmark, explicit owner approval, and financial safety
verification pass. A zero-referral claim is INVALID if any tested field is wrong,
missing or lacks source evidence.
Favor small, reversible changes over new hosted systems or paid integrations.

## Operational Constraints

- Target use: Arabic/English scanned and text PDFs and medical invoice images.
- Existing baseline: 4,895/5,776 correct fields (84.75%) and 99 extra rows on
  300 synthetic invoices. This is a historical benchmark, NOT production accuracy.
- Target: no human referrals AND zero erroneous, missing, invented or unsupported
  fields on a defined independently scored acceptance dataset. An unresolved
  document is a failing result, not a success with renamed errors.
- A literal 100% on arbitrary real-world scans cannot be guaranteed. The goal
  is zero wrong/missing/invented extracted fields and zero referrals on explicitly
  defined holdouts, plus published recall, precision, provenance and error counts.
  Failure is not hidden, relabeled or passed through.
- No unapproved paid OCR services, external PHI uploads, or automatic claim actions.

## Delivery and Acceptance Gates

1. Define a measurable specification and acceptance dataset before changing code.
2. Run existing regressions and record environment-caused skips separately from
   actual algorithmic failures.
3. Add a test that reproduces the defect; implement the smallest evidence-preserving
   correction and compare both true-positive and false-positive item counts.
4. Require all applicable CI checks and holdout comparisons to pass; investigate
   any correctness regression instead of weakening assertions.
5. Publish a transparent READY/BLOCKED report. READY requires every field in
   the defined holdout correct and evidence-linked, zero invented rows and zero
   manual referrals, and explicit owner approval. Never claim universal
   flawless OCR from a finite synthetic test; no implicit financial automation.

## Governance

This constitution governs MDIA specifications, plans, tasks, code reviews, and
acceptance. Amendments require a documented rationale and owner approval;
MAJOR versions remove/redefine guarantees, MINOR versions add principles or
material rules, and PATCH versions clarify wording. Every pull request MUST
verify affected principles and record evidence of the corresponding gates.

**Version**: 2.0.0 | **Ratified**: 2026-10-28 | **Last Amended**: 2026-10-29

**Amendment reason**: Owner rejected zero-human routing with a machine-error ledger;
the acceptance requirement is simultaneous 0% wrong/missing fields and 0% manual
referrals. Prior wording requiring human referrals no longer governs this feature.
