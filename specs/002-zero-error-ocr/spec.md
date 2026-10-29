# Feature Specification: Fully automatic medical-invoice OCR with zero extraction errors

**Feature**: 002-zero-error-ocr
**Date**: 2026-10-29
**Status**: ACTIVE REQUIREMENTS / NOT ACCEPTED
**Owner decision**: Zero human handoffs is acceptable ONLY when there are zero wrong, missing, invented, or unsupported values. A machine-error ledger, blocked-unresolved status, or renamed review queue is NOT a solution.

## User outcomes

1. Upload an Arabic or English invoice PDF/image and receive every printed invoice line, quantity, unit price, line total, patient and invoice identifier and grand total exactly as printed, with independently grounded source evidence.
2. The program automatically repeats localized OCR and reassembles existing source text where necessary, using independent recognition evidence. It never guesses a value from totals, rules or example ground truth.
3. A previously correct field or invoice row cannot be destroyed by an improvement in another field.
4. Zero manual repair or referral for a passing invoice. If even one field is wrong/missing/unproved, acceptance FAILS; do not label it a success.

## Functional requirements

- **FR-001** The release gate MUST evaluate all 300 original frozen synthetic PDF invoices, 5,776 expected fields, in the same seed/layout/representation, with real local PaddleOCR and source-linked evidence.
- **FR-002** The gate MUST accept ONLY if all **5,776 of 5,776** expected fields exactly match independently fixed ground truth, no printed row is missing, and **zero extra/fabricated rows** appear.
- **FR-003** The gate MUST reject **any** missed field, wrong numeric/Arabic character, mislinked invoice service, failed OCR page, absent/cross-row evidence, or human referral. A zero-human count without complete correctness MUST fail.
- **FR-004** Corrections MUST be sourced from the original document or independent source-crop OCR, preserve the original raw text and previous evidence, and include verification of page/row/location. No arithmetic-only inference of a printed medical amount.
- **FR-005** Validate both the unheaded Arabic layouts and text-layer PDFs without corrupting originally correct names or financial amounts.
- **FR-006** An improvement requires a frozen fieldwise comparison: no previously correct field lost and no new false invoice service row.
- **FR-007** Tests MUST include signed/decimal values, Arabic-Indic digits, Persian/Arabic yeh ambiguity, amounts missing decimal separators, two-page invoices, split rows, merged words and incomplete source geometry.
- **FR-008** Spec Kit's spec/plan/tasks MUST reflect this owner requirement; PR #26's zero-routing ledger is rejected and may not be presented as accepted zero-error automation.

## Current baseline and measurable acceptance

The last independently confirmed frozen benchmark is **5,504/5,776 exact = 95.29%**, leaving **272 mismatches**. This is a synthetic-only score. The new zero-error gate is in `scripts/check_zero_error300.py` and MUST produce BLOCKED on this baseline, not PASS.

**Pass conditions simultaneously:** 300/300 processed; 5,776/5,776 exact correct with linked evidence; 0 missing; 0 wrong; 0 invented rows; 0 manual referrals; 0 page failures; no regressions.

**Not claimed:** 100% accuracy on all unseen real medical documents. Separate licensed, de-identified Arabic/English hospital invoices and evidence-geometry validation are necessary before declaring production reliability.

## Failure transparency

Failures remain visible in developer/test diagnostics so they can actually be fixed. Merely recording them or disabling human-review notifications never satisfies this feature. No financial payment, coverage, or clinical decision is automatically approved.
