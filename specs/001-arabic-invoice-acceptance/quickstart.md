# Quickstart: Verify MDIA Release Quality Gates

1. Run fast deterministic contract tests (no PaddleOCR weights, network, or patient data):

   ```bash
   python -m unittest tests.test_invoice300_acceptance -v
   ```

2. Run the existing stacked-header regression with Arabic dependencies installed:

   ```bash
   python -m unittest tests.test_hard.Hard.test_h2_two_line_header_stacked_labels_negative_amounts -v
   ```

3. Generate full score reports with existing GitHub Actions workflow `MDIA release acceptance - 300 real PaddleOCR invoice PDFs`, selecting the desired candidate branch. Ensure six completed artifacts were produced; do not claim a result if a shard failed.

4. Download the six `results.json` files locally and run the evaluator with the exact six paths (order arbitrary):

   ```bash
   python -m scripts.check_invoice300_acceptance /path/to/shard0/results.json /path/to/shard1/results.json /path/to/shard2/results.json /path/to/shard3/results.json /path/to/shard4/results.json /path/to/shard5/results.json
   ```

5. Check `status`, `reasons`, per-layout counts and exit code. Even `PASS` is **synthetic acceptance only**, not a release for automated medical or financial decisions.

### Audited baseline check performed on 2026-10-28

- Downloaded the six original synthetic artifacts from GitHub Actions run `40180808910` (not new OCR inference).
- Ran the evaluator over all six original `results.json` files; verdict **PASS** with exactly **4,895/5,776** correct fields and **99** false extra rows.
- Stored only correctness bitstrings and historical extra-row counts in `scripts/baselines/invoice300_paddle_v1.json`; no source text or patient files are committed.
- An explicit test demonstrates that a newly correct field elsewhere cannot hide the loss of a historically correct field.

## Known current environment limitation

This scratch environment has Tesseract `eng` but not `ara`, and sandboxed local socket creation can be restricted. Full OCR and HTTP tests must run in their configured CI/Windows/Docker environment; environmental failures must not be mislabeled as parser regressions.
