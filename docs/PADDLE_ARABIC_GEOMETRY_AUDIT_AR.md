# MDIA — Arabic OCR Evidence Geometry Audit (2026-10-25)

**Status:** Experimental, synthetic data only. **No merge / deploy.**

## Where
Repository: `overurdream-collab/OCR_deepseak`  
Branch: `experiment/paddleocr-arabic`  
Draft PR: https://github.com/overurdream-collab/OCR_deepseak/pull/4

## Why
The previous structured extraction comparison found **29/30** field values with PaddleOCR vs **15/30** with Tesseract, but PaddleOCR derives individual token rectangles by *proportional interpolation inside detected line rectangles*. A valid `evidence_id` or bbox does **not** prove that a highlighted price or medicine is in the correct pixel location.

## Added verification
- `scripts/audit_arabic_geometry.py` renders original synthetic PDFs and draws all available field-evidence rectangles.
- **Blue:** expected source-row center, derived independently from the synthetic PDF generator's authored line layout.
- **Green:** extracted value agrees with the synthetic reference **and** the center of its evidence is within 8 PDF points of the expected row.
- **Red:** a value mismatch or incorrect source row; missing boxes are counted as missing and not falsely shown as correct.
- Six Arabic fixtures: two original invoices (shaped/visual), original prescription, and three further variations (Eastern Arabic numerals, diacritics, logically-ordered Arabic prescription).
- `tests/test_arabic_geometry_audit.py` checks wrong-page evidence, missing/invalid rectangles, wrong-row placement, and mismatched invoice values.
- GitHub Actions stores both the structured JSON report and all source-page PNG overlays under the **paddle-arabic-synthetic-comparison** artifact.

## Scope of the metric
The `row_consistent_values` number means **field-value equality plus evidence Y alignment with an independently authored synthetic source line**. It **does not verify x positions, token localization accuracy, clinical accuracy, or real hospital document performance**. In PaddleOCR, all token-level x positions remain estimated; require human review.

### Local prepublication check (Tesseract only)
6 synthetic PDFs × 2 invoice items / medicine entries as applicable; **20/54** exact target values found, **20/54** with source-row consistency (no wrong-row hits among found matches). Arabic scans and prescriptions remain weak in the local Tesseract run. This local test **did not run PaddleOCR**.

## To reproduce
```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m scripts.audit_arabic_geometry --engines tesseract --output results/arabic_geometry_tesseract.json --image-dir results/geometry_tesseract
```
Run both engines only with real PaddleOCR runtime:
```bash
python -m scripts.audit_arabic_geometry --engines tesseract paddle_arabic --output results/arabic_geometry_audit.json --image-dir results/geometry_overlays
```

## Unverified or blocked
- Result of **live CI geometry audit on this exact SHA** must be read from the GitHub workflow and artifacts; don't assume pass because previous CI passed.
- Need independent **word-level** geometric ground truth before claiming exact pixel-position correctness. This audit only checks the *row*.
- Need more document layouts and scanned real-world de-identified PDFs, with medical privacy and human review.
- Do not switch the default engine from Tesseract or promote to production based only on these artificial samples.


## Source-evidence chain hardening (2026-10-25)

Additional negative controls ensure that a correct value on the correct Y row
**cannot pass** with the wrong evidence ID, a mismatched raw-to-matched_text,
empty source-line text, or both the field and evidence pointing to a wrong page.
The geometry JSON separately reports `evidence_chain_valid_values`.
This validates **internal consistency only**; it is not independent proof that
the source text was accurately transcribed or that an interpolated token rectangle
contains precisely the characters of its claimed field.

Previous verified run: https://github.com/overurdream-collab/OCR_deepseak/actions/runs/40134405268
reported PaddleOCR 52/54 and Tesseract 20/54 source-row-consistent
synthetic values. The hardened implementation requires a new CI run on its
exact SHA before those figures can be reasserted as current.
