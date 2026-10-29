# Implementation Plan: MDIA zero-error OCR

**Feature**: 002-zero-error-ocr | **2026-10-29** | **Status**: plan approved for research/testing, not release-ready

## Measurable approach

1. **Fix the measurement first**. Use frozen 300 source PDFs and `scripts/check_zero_error300.py`, with non-regression and linked-evidence checks. A BLOCKED result on 5,504/5,776 is an expected honest baseline.
2. **Rank causes, not guesses**. Export every mismatch with source PDF, expected field, extracted field, row and evidence ID for local synthetic diagnostics. Distinguish OCR recognition from table association and decimal parsing.
3. **Repair independent evidence only**. Prioritize largest categories by exact source pixel/word detection: 132 quantities; 42 patient names (including Persian/Arabic yeh); 41 unit prices; 30 line totals; 12 service names; 11 grand totals; 4 invoice identifiers. These counts describe benchmark mismatches, not necessarily independent root causes.
4. **Verify each targeted repair** via reproducible unit test, independent source-crop read and all 300 original PDFs; reject regressions.
5. **Prove complete correctness** on the frozen dataset and subsequently on approved, anonymized real PDFs. No 100% universal guarantee from only one synthetic set.

## Quality gates

- **Gate A** Existing regression suites; prove source evidence and original-raw preservation.
- **Gate B** Frozen 300 original PDFs with real local OCR; each field checked, no altered ground truth.
- **Gate C** Independent `check_zero_error300.py` accepts ONLY 5776/5776 exact, zero spurious rows, zero human referrals, zero invalid evidence; otherwise BLOCKED.
- **Gate D** Permissioned de-identified real invoices and human-approved operational release decision (release decision only, not manual invoice correction). No automatic financial claim decisions.

## Project boundaries and resources

Reuse the local Python/Windows OCR pipeline with PaddleOCR, Tesseract, original-document crop evidence, and existing extraction/validation. Spec Kit guides design/tasks; **it is not the OCR engine**. Avoid patient data in GitHub/CI, paid tools and production deployment. PRs remain drafts, main unchanged.

## Evidence and constraints

Current synthetic benchmark: 5,504/5,776 exact = 95.29%, 272 incorrect/missing. Existing PR #27 quality gate intentionally refuses to convert 0 referral into 100% reading. Follow-on features must actually reduce these errors. If some source is intrinsically illegible, do not invent its contents or call it zero-error.
