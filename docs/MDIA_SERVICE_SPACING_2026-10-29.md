# MDIA — source-preserving service-word boundary repair

**2026-10-29 — Isolated Draft PR #24.** No production merge. Stacked on Draft PR #23; its invoice identifier candidate is independently under test.

## Verified input source and local isolated evaluation

Used the source-token trace produced by **actual PaddleOCR on 8 reproducibly generated synthetic PDFs**, GitHub run [40783748550](https://github.com/overurdream-collab/OCR_deepseak/actions/runs/40783748550), artifact `mdia-missing-fields-synthetic-evidence`. That trace includes printed synthetic invoice row names and actual extracted invoice item values. An isolated local Python run imported the exact spacing algorithm and compared expected service names to values before/after.

| Measure | Before | After |
| --- | ---: | ---: |
| Expected synthetic service rows across 8 selected PDFs | 41 | 41 |
| Exact matched service names | 36 | **40** |
| Newly exact service names | — | **4** |
| Previously exact names lost | — | **0 in this 8-PDF trace** |
| Name values modified | 0 | 5 |

Examples of **source-visible, whitespace-only** fixes:
- `تخطيطقلب` → `تخطيط قلب` (Arabic letters unchanged).
- `تح ليل سكر صائم` → `تحليل سكر صائم`.
- `تحليل دمشامل` → `تحليل دم شامل`.
- `CreatinineTest` → `Creatinine Test`.

One additional value `تحليل وظائ ف الكلی` → `تحليل وظائف الكلی` was **NOT** a complete exact match with printed `تحليل وظائف الكلى`, because the final Persian/Arabic yeh/kaf spelling remains ambiguous. The spacing fixer does **not** change this source glyph or bypass the independent Arabic script uncertainty review. These numbers describe the 8-case archived OCR trace, **not** the complete 300-PDF accuracy.

## Safety guarantees

- Only alters the extraction output `service_name.value` for an existing, evidence-linked, extracted invoice row. `raw` and original source evidence never change, and the original output value is attached as `spacing_repair.original_value`.
- No numeric changes, patient names, diagnoses, medications, invoice identifiers or fabricated rows.
- Never adds/removes/reorders a single non-whitespace character; unknown/ambiguous combinations stay unchanged.
- A tiny conservative standalone medical-word vocabulary is used for Arabic; only unique word boundary splits are accepted; Latin lowercase-to-uppercase transitions are formatting only.
- Previous review requirements and original source coordinate caveats remain.
- Existing source geometry for PaddleOCR word tokens is interpolated unless separately verified. Whitespace reconstruction does not establish source location.
- **Production use remains blocked** pending frozen-300 strict fieldwise success, permitted anonymized real invoices, and evidence locator verification.

## Full 300-case release guard

Workflow `.github/workflows/mdia-service-spacing-300.yml` runs six shards of real PaddleOCR/Tesseract, compares against the **verified 5,384 / 5,776 = 93.21%** baseline from run [40784369818](https://github.com/overurdream-collab/OCR_deepseak/actions/runs/40784369818), and fails if any previously correct field is lost, any false extra invoice row appears, or an extracted correct field lacks linked source evidence.

**Until that workflow reports success, 93.21% remains the last verified aggregate and no 300-case gains are claimed.** The earlier PR #23 invoice ID candidate is unverified on 300 cases at the time of this report, and this stacked branch must not attribute gains to only one of the two changes.
