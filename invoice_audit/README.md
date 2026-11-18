# Invoice Audit Engine — P0 deterministic prototype

**Status:** experimental, isolated three-way matching core. **NOT PRODUCTION READY.**
Reference: [Arabic vision, roadmap and acceptance gates](../docs/INVOICE_AUDIT_VISION_PLAN_ACCEPTANCE_AR.md) (PR #35 until merged).

## Completed in this branch
- Pure Python `invoice_audit.audit(po, grn, invoice)` returns one of `VERIFIED_MATCH`, `VERIFIED_EXCEPTION`, `UNVERIFIABLE`.
- No payment authorization: `approval` is always `false`.
- Decimal string accounting (never a binary float).
- Basic single-order, complete-receipt, single-invoice cases only, no other charges.
- Flags excess/short invoiced vs received quantity, excess vs ordered quantity, unit price, per-line arithmetic and invoice total discrepancies.
- Rejects missing/invalid evidence, manual-review pending, unsupported/ambiguous currency, unknown line, duplicate SKU+unit, negative/nonfinite values, unsupported multi-document scopes.
- Isolated synthetic regression tests: `python -m unittest tests.test_invoice_audit -v`.

## CRITICAL trust-boundary gap

The input data contract includes `verification="verified"`, evidence_id, SHA-256 *string*, and source_locator. **Currently this module only checks their presence/shape.** It does **not** compare SHA-256 to actual source bytes, validate whether the locator contains the value, validate signer identity, or authenticate reviewer attestations. A malicious/mistaken caller can forge the fields. Therefore `VERIFIED_MATCH` is only a **conditional result for a caller-supplied supposedly verified dataset**, **NOT independent proof of a correct source invoice**. **No financial or operational automation may consume this outcome yet.** The trusted provenance adapter and source-store verification MUST be built and tested before production or public APIs.

The module is independent of MDIA and does **not** connect to MDIA's raw OCR output; OCR data must remain provisional until an independently verifiable evidence chain and permitted human review are completed.

## Explicit limits
- Fixed currency allowlist `USD/SAR/YER`, no conversion or currency aggregation.
- No additional tax/discount/shipping or multiple PO/GRN/invoices, returns, credits, partial allocation or tolerance rules.
- No database, UI, document ingestion, source-binding layer, tenant isolation, API auth, signature verification, ERP integration, or payment actions.
- No benchmark on actual user documents. Tests use synthetic in-memory dictionaries only.
- No OCR-quality claim: the historical MDIA 300-invoice failures are still unresolved.
- Do NOT merge PR #32 or reduce MDIA acceptance gates as part of this prototype.

## Next P0 implementation
1. Fetch raw documents from controlled immutable storage, calculate SHA-256 from bytes, verify each field against independently checked source location and store signed reviewer attestations.
2. Define strict schema and typed adapters for XML/Excel/PDF; fail closed if extraction is incomplete or unsupported.
3. Test source tampering, forged evidence ids/hashes/locations, document-signature errors, multiple receipt allocations, currency and unit conversion, tax/discount rules, concurrency, access control, and audit log integrity.
4. Re-run independent holdout datasets; verify accuracy and false-match rate with counts and denominators.

No tests claimed passed until GitHub Actions returns a recorded result for this branch SHA.
