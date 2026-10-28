# MDIA — Isolated Arabic Table Model Trial / تجربة الجداول العربية

**Date:** 2026-10-28. **Status:** EXPERIMENT / NOT FOR AUTO-MERGE. **Repository chain:** PR #16 Spec Kit → PR #17 Arabic normalization → PR #18 OCR engine comparison → this isolated experiment.

## What was learned

The earlier local, **cropped table-region** experiment used nine synthetic Arabic invoice examples, 168 target fields. The light table model yielded **104/168 (61.90%)** with the initial table orientation behavior; turning **table orientation classification off** improved its result to **145/168 (86.31%)**. The existing PaddleOCR pipeline correctly extracted **151/168 (89.88%)** on the same nine samples. These are small, experimental measurements from the earlier session, not a new GitHub CI benchmark or a 300-case release score. The exact saved per-case outputs and the lighter model's checkpoint identifier were not available when preparing this new isolated gate; do not claim that the new script reproduces those scores. The 300-case verified PaddleOCR baseline remains **5,113/5,776 (88.52%)** on synthetic PDFs.

The full PaddleOCR-VL-1.6 pipeline was also tried in a separate CPU environment and exited under ~9.7 GiB of available RAM; this is a **hardware limit in that environment**, not evidence that VL performs poorly at reading Arabic. No model integration was approved from that attempt.

PaddleOCR's official [PP-StructureV3 documentation](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PP-StructureV3.html) exposes `use_table_orientation_classify=False` and its raw `table_res_list[*].pred_html`, `cell_box_list` and `table_ocr_pred`. The new runner is designed for that **published interface**, and is not represented as a replay of the exact previous lightweight-model checkpoint.

## Isolated trial, without changing the MDIA OCR runtime

1. In a **separate local Python environment** install the CPU-capable PaddleOCR/PP-StructureV3 dependencies from the official versioned instructions. Keep system MDIA packages untouched. Weights may be downloaded by the official library; verify free space and memory.
2. Crop a **synthetic** invoice table to a PNG/JPEG. Do not use actual patient information in a shared runner. The model is opt-in and the orientation classifier is explicitly disabled.
3. Run `python -m scripts.run_ppstructure_crop_trial --input synthetic_table_crop.png --output table_raw.json`.
4. Inspect or evaluate that saved output: `python -m scripts.table_model_review_gate --input table_raw.json --columns name=3,qty=2,unit_price=1,total=0 --first-data-row 1 --output table_review.json`. Adjust explicit column mapping to the **actual visual HTML order** (0-based left-to-right), never guess it programmatically.
5. `table_review.json` always returns `BLOCKED_FOR_AUTOMATIC_PROMOTION` with `needs_review` row suggestions. The gate never copies or replaces an amount in MDIA. Even correct `qty × unit_price = total` is **not proof of transcription**.

## Safety requirements and unresolved issues

- `pred_html` is a candidate's OCR interpretation. Its `cell_box_list` is not automatically accepted as source field provenance. Geometry needs a verified mapping from crop pixel coordinates back to source page plus a direct text-cell association; until then **zero field evidence locations qualify**.
- An empty/missing table region, merged `rowspan`/`colspan`, unequal row widths, missing columns, or ambiguous comma/thousands separators blocks automatic interpretation. Arabic and Persian digits are accepted **only for arithmetic checks** and their raw representations remain unchanged.
- A cell containing no price must not borrow another row's price. Arithmetic inconsistencies are flagged; numeric values are never corrected. Review is mandatory for every proposed row.
- The 9-sample experiment **lost 6 fields** relative to PaddleOCR. The new candidate remains **BLOCKED** pending a full, frozen, per-field, non-regression evaluation on all 300 synthetic PDFs and an independent anonymized real-invoice evaluation.
- The earlier local full test suite had environmental PDF rendering/font and network-port issues; the isolated tests in this PR do not claim to fix those unrelated blockers. Run the existing MDIA full CI after PR creation and record failures separately.
- Real patient data stays local, not committed, not published as GitHub CI artifacts and not transmitted to hosted OCR APIs.

## Acceptance steps for future experimental promotion

The candidate must beat or at least preserve the **88.52%** frozen synthetic baseline **with no previously correct field lost**, no extra false billing rows, no weakening of review, and verified source geometry. A measured gain on one type of document is not permission to switch the model for other layouts. An independent validation set of redacted, permitted real documents is essential before production use. PR remains draft until these steps are proven.
