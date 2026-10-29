# MDIA — original-source row repairs, 2026-10-29

Release status: **NOT ACCEPTED**. No claim of 100%, no merge, no review suppression.

## Verified starting point

PR #28 at `5fbf98f51a2ac0b1df5f609a18743849faa6fe5a`. The completed original run [40796149371](https://github.com/overurdream-collab/OCR_deepseak/actions/runs/40796149371) reports **5510/5776**, six gains over 5504, zero losses and zero new extra rows. Its green non-regression check was NOT the absolute zero-error gate. There remain 266 incorrect/missing fields in that historical result.

## Actual defects repaired

1. A `.45` maximum description-to-price gap rejected an independently printed quantity in a valid source row. For `en_compact_12`, the observed gap was `.45667`. The bounded corridor now permits `.65`, retaining observed same-row prices and a SINGLE printed digit. Ambiguity is checked BEFORE arithmetic: a printed 2 plus a printed 3 cannot be resolved by choosing whichever fits multiplication. Direct replay of the real original PDF/Paddle cache recovered `item.3.qty`, **18/19 -> 19/19**.
2. Numeric re-OCR padded the source box vertically by 60%, including portions of quantities from neighboring invoice rows. The actual crop for the above case contained a central 3 and parts of adjacent digits. With the old crop, readings included 1, 7 and 3, and confirmation failed. Row-bounded padding produced six independent preprocessing/language/PSM readings of the printed **3**, with confidence **.96-.97**, without relaxing any acceptance thresholds. Source bbox positions are mapped from Tesseract to original PDF coordinates.
3. A `not_found` quantity had no original glyph/evidence to trigger re-OCR. A separate narrow recovery now requires an explicitly observed Qty/Quantity/الكمية header, a unique physical column, same-page/same-row description and both amounts, no stated line discount, and two reproducible source-pixel digit readings. Arithmetic corroborates a printed digit and never generates it. Source replay of scanned `en_standard_37` recovered `item.5.qty`, **26/27 -> 27/27**. New evidence links all three row anchors and the actual header. Correct existing quantities are untouched. A conflicting extracted numeric token may be independently re-read at the explicit source column; the original raw and evidence are preserved.
4. An already extracted short numeric OCR token can be re-read only when its row multiplication conflicts. Correct numeric quantities are not re-read; the original raw/evidence remains preserved. Adoption still needs two source reads and the existing disagreement/confidence checks. The explicit source-column path corrected the actual `en_standard_29` quantity from 2 to the independently read 3, completing **27/27** fields. No full-dataset gain is claimed before aggregation.

5. A fully printed Arabic charge row was discarded because its literal quantity had Paddle confidence `.597` while all other cells were clear. The existing two-row column anchors now also retain a literal low-confidence positive integer in the quantity column (candidate range `.40-.65`, with price/total/description guards unchanged). This is NOT a lower final OCR approval threshold: the same independent source-digit verification and all review requirements remain. A paired real-Paddle original-PDF probe changes **ar_shaped_18: 19/23 -> 23/23**, restoring the whole fifth printed charge, with **5/5 rows**, zero extra rows, and identical PDF/cache SHA256 values. See `docs/evidence/source_row_ar_shaped_18.{json,pdf}`.
6. Integrated the already source-probed PR #30 invoice-ID suffix correction and its tests. It preserves original values/evidence and only accepts the complete unambiguous observed header identifier. This is included in the candidate and excluded from the exact baseline extraction module in the paired harness.

## Rejected external approach

Reviewed [PaddleX #5030](https://github.com/PaddlePaddle/PaddleX/pull/5030), merged upstream, and tested real `return_word_box=True` with PaddleOCR 3.7.0 / PaddleX 3.7.2 on six source layouts. The word output did not satisfy exact line-token coverage in these six cases. The strict experimental adapter failed these cases and was removed. A subsequent raw-result inspection confirmed that the upstream Arabic word output groups the entire Arabic line into a single reversed string; it does not supply the required individual Arabic word regions. No production switch or false word-verification flag from that experiment is retained.

## Executed validation

- Full final integrated local suite: **266 run, 265 PASS, 1 SKIP**, 192.724 seconds. Local Tesseract Arabic+English, actual Arabic shaping libraries and Amiri font were available.
- Original-PDF crop regression exercises real local Tesseract, not a mocked digit prediction.
- Missing-quantity guards cover no printed digit, no header, conflicting columns, neighboring row, missing amounts, discount, wrong engine, existing quantity, single preparation, and conflicting strong readings.
- Compiled changed Python; `git diff --check` clean.

## Completed first 300-case candidate (earlier commit)

Real full-300 run [40902985455](https://github.com/overurdream-collab/OCR_deepseak/actions/runs/40902985455), commit `86749efa`, completed. Independently downloaded all six candidate shards and all six PR28 baseline shards; compared every case, field identity and expected value.

- **5510 -> 5545 / 5776 (96.00%)**, **35 gains, zero losses**, zero new extra rows and no matched field without linked evidence.
- Absolute gate still **BLOCKED**: **231** incorrect/missing fields, **11** unmatched extra rows and **300** human-referral documents; zero failed pages.
- This result predates the later invoice-ID integration, conflicting quantity-column repair and low-confidence literal-row restoration. It must NOT be quoted as a full validation of those later changes.
- Machine-readable comparison and remaining errors by field: `docs/evidence/source_row_first_300_result.json`.

## Full acceptance protocol

`compare_native_gap300.py` loads baseline extraction, table and quantity modules from the exact starting commit, disables the new missing-field path only for that baseline, and runs both full extraction paths on the same original PDF and cached real PaddleOCR pages. Candidate must not invoke PaddleOCR again or change the OCR cache. Both reports carry PDF and cache SHA256 values.

`summarize_source_row_repair300.py` validates all 300 identities and all 5776 checks, rejects source/cache changes, reports every gained/lost field and new extra row, and separately runs the unchanged absolute gate. CI's final step **requires perfection**, so a partial improvement remains BLOCKED.

## Latest full 300-case result — HEAD 5a24434f (run 40907533409)

The paired full-dataset CI has now completed on the current PR head. All six source-PDF comparison shards succeeded; the absolute acceptance job correctly failed because the strict gate is not met: [workflow run 40907533409](https://github.com/overurdream-collab/OCR_deepseak/actions/runs/40907533409).

- Baseline: **5510/5776** exact fields.
- Candidate: **5567/5776** exact fields (**96.38%**), **+57 gains, zero lost correct fields**.
- Remaining: **209 wrong/missing fields**, **11 unmatched extra rows**, **300/300 documents still require human review**, zero page failures, zero evidence-link gaps, and zero newly introduced extra rows.
- Missing fields: `invoice.total` 11, `name` 8, `patient.name` 28, `price` 8, `qty` 81, `total` 8.
- Incorrect fields: `patient.name` 14, `price` 29, `qty` 4, `total` 18. The previous baseline's invoice-number mismatches are no longer present in the candidate error list.
- Final status: **BLOCKED**. This is a measured improvement, not release acceptance.

## Next engineering blocker

The blanket referral is currently added in `mdia/pipeline.py` for every Paddle-Arabic OCR page because `mdia/paddle_arabic.py` assigns `geometry_source="line_interpolated"` to token rectangles estimated from line boxes. `mdia/word_localization.py` can match some tokens to Tesseract boxes, but the code and its own module documentation explicitly say cross-engine matches are not ground-truth verification. Therefore, simply deleting the referral or setting `word_box_verified=True` would create a false PASS and is not an acceptable fix.

Next work must implement and test a real source-localization path (or a verified native PDF text-layer path where the PDF genuinely contains one), with tests proving that each accepted field's evidence bbox encloses the correct printed token and does not overlap a neighboring value/row. Only after that should review referrals be recalculated from actual evidence quality. Separately, the 209 field mismatches and 11 spurious rows still need source-backed repairs. No merge, deployment, hidden handoff, error-ledger substitution, invented row, or arithmetic-only fill has occurred.


## Artifact-level error decomposition from all six completed shards

The six candidate ZIP artifacts for run 40907533409 were downloaded and inspected independently. They contain exactly 300 unique case results. The 209 failed checks decompose as follows:

| Field group | Failed checks | Missing | Wrong |
|---|---:|---:|---:|
| Patient name | 42 | 28 | 14 |
| Item quantity | 85 | 81 | 4 |
| Item unit price | 37 | 8 | 29 |
| Item line total | 26 | 8 | 18 |
| Item description/name | 8 | 8 | 0 |
| Invoice total | 11 | 11 | 0 |
| **Total** | **209** | **144** | **65** |

The table reconciles to the CI's 209 errors/missing fields. It helps prioritize source-backed work: quantities account for the largest single field group, while unit-price and line-total errors are often incorrect rather than absent. Some wrong amounts exhibit a scale error (for example, a unit price read as 4800 instead of the printed 48 while the row total remains 144). This is a diagnostic signal only: arithmetic must not overwrite the printed amount. The repair must re-read the original source crop and preserve the original reading/evidence.

Patient-name errors are a separate Arabic OCR/normalization issue: some are missing; others preserve a visually similar but non-identical Arabic character (for example, ليلی vs ليلى). They must not be normalized to the expected value without source glyph evidence. The 11 extra rows are tracked separately from the 209 field checks and remain a hard blocker.

This decomposition is based on the downloaded run artifacts, not on a new code change or a new test run. It does not change the acceptance status.
