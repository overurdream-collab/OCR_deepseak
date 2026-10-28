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
