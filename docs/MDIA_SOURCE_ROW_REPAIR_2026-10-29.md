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

The full updated 300-case acceptance has not yet completed for this change. Partial local replays and the historical 5510 result must not be presented as the final updated score. All source-location, arithmetic and review requirements remain visible. No error ledger, hidden handoff, invented row, or inferred quantity was introduced.
