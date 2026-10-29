# MDIA — Zero-human-handoff mode (safe isolated pilot)

**Status:** Draft PR #26. Not merged to `main`; no hospital/patient production use.

## User requirement

The MDIA document reader should operate without human escalation (0% human handoffs). **Zero referrals is not the same as 100% document accuracy.** An unreadable medical service or quantity must NOT be turned into an invented number or silently approved. Medical/financial claims decisions remain a distinct downstream process and are never approved by this reader.

## Activation

Run locally (synthetic invoices only for this pilot) with `MDIA_ZERO_HUMAN_MODE=1`, or explicitly invoke `process_job(..., zero_human=True)`. The default remains legacy until full validation and explicit promotion. No paid OCR API, no secret, and no production account is required.

The existing workflow performs original PDF reading, PaddleOCR, secondary Tesseract quantity OCR where eligible, source-preserving service label spacing correction, deterministic arithmetic validation, and source-warning collection. The new policy is applied **after these real automated passes**, not instead of them.

## States and guarantees

- Fully evidenced and self-consistent extraction: `processing_status=completed`, `extraction_ready=true`, `human_handoff_count=0`, `financial_approval=false`. This is *extraction readiness*, not medical/financial payment approval.
- Any unproven value, arithmetic mismatch, missing required invoice item, unlocalized PaddleOCR source word, OCR page failure, or conflicting cross-document patient identity: `processing_status=blocked_unresolved`, `extraction_ready=false`, `financial_approval=false`. Its raw bytes, evidence and causes remain in `machine_unresolved_checks`.
- Instead of the human queue, `requires_human_review=[]`. This must **never** be interpreted as clean unless `extraction_ready=true`.
- An uncertain field is marked `verification=machine_unresolved`, preserving `original_verification=needs_review` and the original OCR value, page and evidence.
- Each machine exception explicitly records `automatic_retries_executed=0` when no additional attempt took place. This mode is **NOT** an asynchronous retry scheduler. A system that cannot prove a field must stop that output, not assert an unperformed repair.
- Source word position uncertainty is not just discarded. PaddleOCR currently interpolates word boxes from OCR line geometry and can make a text-exact result still unverified for original-page traceability.
- Page errors or unresolved cross-document identity conflicts block output despite 0 human referrals.

## Acceptance gates

1. Run code/test policy suite and schema comparison (CI workflow `mdia-zero-human-pilot.yml`).
2. Run 300 real-PaddleOCR synthetic invoices with mode enabled; verify **zero human queues, zero human referrals, nonzero blocker ledger for genuinely incomplete/unverified cases, and no loss of exact source-backed fields vs the latest 95.29% frozen benchmark**. A numerically accurate synthetic answer is not enough to approve source geometry.
3. Test authorized de-identified real Arabic and English PDFs, especially scans, ambiguous quantities, poor image contrast, clinical names, table omissions and missing page evidence.
4. No merge, production integration or clinical/financial release without explicit authorization.

**Next technical development after this route is proven:** bounded automatic re-reading of unresolved crops and independent word-box localization, followed by measured unresolved-rate reduction. Never implement infinite retries, fake certainty, or an invisible human handoff.
