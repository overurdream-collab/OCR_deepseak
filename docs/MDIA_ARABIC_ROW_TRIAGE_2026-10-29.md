# MDIA-ROW-01 — remaining 300-invoice failures after PR #19

**Source:** original completed six-shard real-PaddleOCR synthetic 300-PDF benchmark in [run 40773688662](https://github.com/overurdream-collab/OCR_deepseak/actions/runs/40773688662). This is not a production accuracy report.

## Field-level census

| Layout | Incorrect or missing | Missing (`actual is null`) | Present but incorrect |
| --- | ---: | ---: | ---: |
| `ar_visual` | 171 | 153 | 18 |
| `ar_shaped` | 115 | 97 | 18 |
| `ar_mixed` | 108 | 82 | 26 |
| `en_standard` | 32 | 25 | 7 |
| `en_compact` | 37 | 30 | 7 |
| `en_reordered` | 43 | 36 | 7 |
| **All layouts** | **506** | **423** | **83** |
| **Arabic subtotal** | **394** | **332** | **62** |

Unmatched by field type in Arabic layouts: service/patient name (77), quantity (137), unit price (63), line total/invoice total (105), invoice number (12). Counts include `patient.name` and `invoice.total` under their matching suffix categories; ensure a separate breakdown for billing-row-only failures.

## High-value known reproducible cases

- `ar_shaped_18`: 2 extracted invoice rows versus 5 synthetic source rows; 3 complete invoice items missing.
- `ar_mixed_18`: 4 versus 6; 2 full invoice items missing.
- `ar_visual_48`: 5 versus 6; name matching for 2 synthetic items failed, including one full missing source row.
- `ar_visual_13`: 4 versus 4, but two service names and amounts unlinked; row count alone falsely suggests success.
- `ar_visual_32`: 5 versus 5, but multiple amounts previously had a 100× decimal-loss problem, illustrating a separate OCR-character error.

## Safety-first experimental decision

Do **not** add rows based on expected synthetic truth, a medical dictionary match, arithmetic inference, or the number of rows predicted by a language model. The correct fix must use observed original-source words, verified row locality, explicit three numeric columns and a separately evidenced service description. Preserve the difference between a *missing OCR token* and a *missed row association*.

The isolated real-OCR input trace for `ar_shaped_18`, `ar_mixed_18`, `ar_visual_48` is attached as an artifact of the PR #20 diagnostic workflow; reference the actual trace before selecting a code patch. No human financial decision is authorized based on synthetics.

## Acceptance criteria

- Run isolated synthetic regression cases + full existing MDIA tests.
- Re-run all 300 original synthetic PDFs with real PaddleOCR on all six shards, check every previously-correct field, evidence linkage, human review and extra-row count.
- Report actual new correct / lost fields **by case**, not just an aggregate.
- No PR merge into `main` until explicit user approval and permitted, anonymized real invoices are evaluated.

## Experiment result — branch head bbc5e5e, 300-PDF six-shard acceptance

**Test run:** [GitHub Actions 40776907768](https://github.com/overurdream-collab/OCR_deepseak/actions/runs/40776907768), all six actual PaddleOCR shards + original frozen gate: **SUCCESS**. Existing MDIA CPU regression / Arabic PDF readiness on [run 40776907716](https://github.com/overurdream-collab/OCR_deepseak/actions/runs/40776907716): **SUCCESS**, **179 tests run (178 passed, 1 skipped)**.

Independently downloaded all six new truth-linked reports and compared them field-for-field against the complete six-shard **91.24%** snapshot from PR #19 / run 40773688662 (not the easier historical 84.75% snapshot). Results:

| Metric | Previous PR #19 | Experimental PR #20 |
| --- | ---: | ---: |
| Exact correct / expected | 5,270/5,776 | **5,285/5,776** |
| Exact synthetic score | 91.24% | **91.50%** |
| Newly correct fields | — | **15** |
| Previously correct fields lost | — | **0** |
| Additional false rows | — | **0** |

The 15 newly exact matches consist of **5 service names, 5 observed unit prices, 5 observed line totals**. The unrelated quantities remain unreadable, not auto-corrected. Improvements occurred exclusively in three known synthetic PDFs:

- `ar_shaped_18`: 11/23 → 17/23 fields, +6 (2 source rows' names/prices/totals).
- `ar_mixed_18`: 19/27 → 25/27, +6 (2 source rows).
- `ar_visual_48`: 19/27 → 22/27, +3 (1 source row).

The reference results were not manipulated. Original OCR outputs showed literal Latin `M` in the Arabic quantity column while adjacent prices, totals and clinical service descriptions were intact. The patch in `mdia/tables.py` recovers the *observed text only* if multiple independently parsed neighbor rows establish stable numeric column x positions and same-row tokens pass conservative geometry and confidence tests. It sets the unreadable quantity's text to the original `M`, `status=unreadable`, `verification=needs_review`; it NEVER derives an imagined quantity (even if prices × expected quantity would balance). The raw-source geometry remains interpolated and subject to mandatory human review.

Also prevented summary captions such as `إجمالي الفاتورة` from being treated as billable items when OCR emits the entire caption as a single token instead of separate words. Regression tests cover this false-positive case, low confidence, incorrect column, insufficient anchor rows, unrelated text, and missing unit price.

**NOT approved for financial automation, patient use, or main merge.** The ~91.50% figure is a synthetic benchmark, not guaranteed real-world accuracy. Remaining fields: **491 / 5,776**, of which the lossless 15-field recovery is a precise and reproducible improvement. The project still needs verified field-level source boxes and an independent permitted anonymized set of genuine Arabic medical invoices.
