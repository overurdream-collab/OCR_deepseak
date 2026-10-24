# MDIA Cloud2 — Independent QA (2026-10-24)

**Evidence source:** User-uploaded `mdia_agent_cloud2.zip`, reviewed and executed in a separate sandbox. **This is an audit note, not the project source.** The uploaded application itself has NOT yet been committed to this repository.

## Confirmed
- 37/37 original unit/integration tests passed in the local environment.
- Developer-generated synthetic fixtures: 42/42 field checks, 10/10 invoice line checks; 398/398 matching evidence boxes by the project's own validation method.
- HTTP API roundtrip, PDF OCR (Tesseract) and outputs tested.
- No DeepSeek-OCR 2 implementation was present in this uploaded application. It uses pdfplumber, pypdfium2, Tesseract and rule-based extraction.

## Independent, never-seen synthetic documents
| Input | Confirmed result | Material defect |
|---|---|---|
| Alternative English bill, 2 lines | Invoice number and total extracted | Only 1/2 line items extracted; patient full name shortened to last word |
| Alternative prescription, 2 medicines | One medicine and diagnosis found | 1/2 medicines omitted; `Rx:` included in medicine name |
| Independent scanned Arabic invoice, 2 lines | OCR captured invoice number, patient and total | 0/2 line items extracted, yet reported completed with no warnings |

**Risk:** Incomplete invoice data can be silently treated as a completed result. This prevents production readiness.

## Environment diagnostic
`python -m mdia.doctor`: PASS for Tesseract, Arabic `ara` traineddata and Arabic font; FAIL for missing `arabic_reshaper` and `python-bidi`, so the true Arabic PDF export path could not be confirmed on this machine. Windows and Docker were not tested.

## Required acceptance gate
1. Upload the FULL application source to a separate GitHub branch.
2. Add independent regression tests for omitted invoice lines, multiple medicines and patient names.
3. Make incomplete extraction trigger `requires_human_review` or equivalent, not silent completion.
4. Run `python -m unittest tests.test_pipeline tests.test_arabic -v` AND `python -m mdia.doctor` with all dependencies present.
5. Verify on the exact commit with GitHub Actions and test the intended Windows/Docker install paths.
6. Do not deploy using real patient documents until these issues are closed.

No production changes, no merge, and no real patient data used.
