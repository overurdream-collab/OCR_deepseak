# Tasks: MDIA zero-error / zero-human extraction

**Feature**: 002-zero-error-ocr | **Status**: IN PROGRESS
**Owner outcome**: Automatic source-exact correction; do not pass or rename errors as unresolved and claim success.

## Phase 1: Truth and safety gates
- [x] T001 Document 100% complete, exact and source-grounded acceptance in `spec.md` (5,776/5,776; 0 missed/false rows; 0 manual referrals).
- [x] T002 Add strict `scripts/check_zero_error300.py` scorer and intentional failure tests in `tests/test_zero_error_acceptance.py`.
- [ ] T003 Verify current draft PR #27 CI gate; investigate and fix any checker *bugs* without relaxing the 100% threshold. Present the actual BLOCKED numbers honestly.
- [ ] T004 Introduce a reproducible source-level per-field diagnostics report for all 272 mismatches, showing whether OCR recognition or table matching caused each failure. Synthetic-only, no real PHI.

## Phase 2: Recover source-backed fields automatically
- [ ] T005 Quantity: analyze and repair the 132 incorrect/missing quantity fields using independent original-PDF word localization, re-OCR and same-row verification; never infer by division alone.
- [ ] T006 Money: repair 41 unit-price and 30 line-total mismatches, including missing decimal punctuation, with independently observed original source glyphs; do not guess a separator from arithmetic.
- [ ] T007 Names: repair 12 remaining invoice service-name mismatches and 42 patient-name mismatches using source OCR. Preserve ambiguous medical `ي/ى/ی` without unsupported substitution.
- [ ] T008 Identify 11 remaining grand-total and 4 invoice-identifier mismatches using exact source lines; confirm no footnote/stray token hijacks the value.
- [ ] T009 Preserve all previously correct values (frozen 5,504 exact) and never add a spurious row while repairing any category.

## Phase 3: End-to-end proof
- [ ] T010 Run full original 300 synthetic PDFs through actual local OCR; publish exact fieldwise gains, losses and evidence linkages.
- [ ] T011 Pass **all** gates simultaneously: 5,776/5,776 exact; 0 incorrect/missing fields; 0 phantom rows; 0 invalid evidence; 0 human referrals; 0 failed pages.
- [ ] T012 Test varied authorized de-identified real medical invoices before any operational readiness claim; explicitly report unseen-layout failures.
- [ ] T013 Review Windows laptop packaging, runtime and local privacy. Keep unapproved merging/deployment off.

## Rules for task completion
Each box is checked ONLY after a linked reproducible code change and passing independent result. A PR opened, code compiled, a green unit test, or a renamed error ledger is not sufficient. There is no claim of universal 100% accuracy from a finite benchmark.
