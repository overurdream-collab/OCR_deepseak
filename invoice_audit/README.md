# Invoice Audit Engine — P0 deterministic prototype

**Status:** experimental, isolated three-way matching core. **NOT PRODUCTION READY.**
Reference: [Arabic vision, roadmap and acceptance gates](../docs/INVOICE_AUDIT_VISION_PLAN_ACCEPTANCE_AR.md) (PR #35 until merged).

## Completed in this branch
- Pure Python `invoice_audit.audit(po, grn, invoice)` returns one of `VERIFIED_MATCH`, `VERIFIED_EXCEPTION`, `UNVERIFIABLE`.
- No payment authorization: `approval` is always `false`.
- Decimal string accounting (never a binary float).
- Basic single-order, complete-receipt, single-invoice cases only, no other charges. Explicit source-evidenced PO and GRN cross-document references are required.
- Structured JSON source adapter (`audit_json_sources`) reads original bytes, rejects unknown fields and JSON numeric literals/duplicate keys, binds exact values to JSON pointers and independently calculates SHA-256 for those bytes. This prevents *transcription drift*, not fraudulent source documents.
- Flags excess/short invoiced vs received quantity, excess vs ordered quantity, unit price, per-line arithmetic and invoice total discrepancies.
- Rejects missing/invalid evidence, manual-review pending, unsupported/ambiguous currency, unknown line, duplicate SKU+unit, negative/nonfinite values, unsupported multi-document scopes.
- Isolated synthetic regression tests: `python -m unittest tests.test_invoice_audit tests.test_invoice_audit_source -v`.

## CRITICAL trust-boundary gap

The low-level `audit()` still accepts caller-supplied `verification="verified"`, evidence_id, SHA-256 *string*, and source_locator; it checks their shape only. An untrusted caller may forge these. **Use `audit_json_sources` for the restricted structured JSON path**, which computes SHA from bytes and derives pointers directly. This still does **not authenticate the supplier or warehouse, prove a delivery occurred, verify digital signatures or persist immutable originals**. `VERIFIED_MATCH` means **matching within the narrow declared data contract** and remains **NOT independent proof of a correct commercial fact**. **No financial or operational automation may consume this outcome yet.** A securely stored trusted provenance adapter, issuer authentication, reviewer attestations and broader validation MUST be added before production.

The module is independent of MDIA and does **not** connect to MDIA's raw OCR output; OCR data must remain provisional until an independently verifiable evidence chain and permitted human review are completed.

## Explicit limits
- Fixed currency allowlist `USD/SAR/YER`, no conversion or currency aggregation.
- No additional tax/discount/shipping or multiple PO/GRN/invoices, returns, credits, partial allocation or tolerance rules.
- No database, UI, PDF/XML ingestion, persistent original storage, tenant isolation, API auth, signature verification, ERP integration, or payment actions. The limited JSON source-binding adapter is not a production intake system.
- No benchmark on actual user documents. Tests use synthetic in-memory dictionaries only.
- No OCR-quality claim: the historical MDIA 300-invoice failures are still unresolved.
- Do NOT merge PR #32 or reduce MDIA acceptance gates as part of this prototype.

## Next P0 implementation
1. Fetch raw documents from controlled immutable storage and independently verify their source provenance and signer/issuer, validate reviewer attestations; never trust unverified caller-provided "verified" status.
2. Define strict schema and typed adapters for XML/Excel/PDF; fail closed if extraction is incomplete or unsupported.
3. Test source tampering, forged evidence ids/hashes/locations, document-signature errors, multiple receipt allocations, currency and unit conversion, tax/discount rules, concurrency, access control, and audit log integrity.
4. Re-run independent holdout datasets; verify accuracy and false-match rate with counts and denominators.

No tests claimed passed until GitHub Actions returns a recorded result for this branch SHA.

## Running the end-to-end proof of concept
```bash
python -m invoice_audit.cli structured --po examples/invoice_audit/po.json --grn examples/invoice_audit/grn.json --invoice examples/invoice_audit/invoice.json
python -m invoice_audit.cli mdia-review --pdf original.pdf --result mdia-result.json
```

The MDIA bridge checks the original PDF bytes against the MDIA report hash, compares page and matched evidence text, and outputs a **manual-review queue only**. It never treats MDIA's `auto_verified` as financial approval. It does not promote OCR data into the structured three-way matching contract.

`invoice_audit.attestation.audit_attested_sources(...)` adds role-scoped HMAC verification of PO, receipt and invoice bytes using independently provisioned secrets. This proves integrity against holders of the provisioned keys **only**. It is not PKI, an official tax e-invoice signature, physical stock receipt proof, approval or an ERP integration. Do not use passwords as signing keys or expose signing secrets to document uploaders.

Operational policy: **No invoice may be paid on the basis of this tool**. Operators must separately verify supplier identity, receipt authenticity and contractual terms; full custody, access control and tested business rules are still needed.
