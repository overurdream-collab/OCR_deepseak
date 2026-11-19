"""Out-of-band HMAC attestations for structured JSON source authenticity.

A trusted administrator provisions role-scoped independent signing keys OUTSIDE
submitted files. A MAC only establishes knowledge of the provisioned shared key,
not a legal digital signature or independent proof of delivery/invoice validity.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Mapping

from .core import UNVERIFIABLE
from .source import audit_json_sources

KINDS = ("po", "grn", "invoice")
DOMAIN = b"INVOICE-AUDIT-SOURCE-v1\x00"


def _bad(reason: str) -> dict:
    return {"status": UNVERIFIABLE, "approval": False, "findings": [],
            "reasons": [reason], "source_authenticity": "failed",
            "ruleset": "invoice-audit-v0.1"}


def source_mac(kind: str, raw: bytes, secret: bytes) -> str:
    """Calculate a source-specific HMAC for trusted local signing services.

    Never submit the secret through an untrusted application interface.
    """
    if kind not in KINDS or not isinstance(raw, bytes) or not isinstance(secret, bytes) or len(secret) < 32:
        raise ValueError("invalid HMAC signing context")
    digest = hashlib.sha256(raw).digest()
    return hmac.new(secret, DOMAIN + kind.encode("ascii") + b"\x00" + digest,
                    hashlib.sha256).hexdigest()


def audit_attested_sources(
    po_bytes: bytes,
    grn_bytes: bytes,
    invoice_bytes: bytes,
    attestations: Mapping[str, dict],
    trusted_keys: Mapping[str, Mapping[str, bytes]],
) -> dict:
    """Verify three differently authorized source roles, then match.

    Keys are provisioned by the caller as trusted local configuration, NOT
    obtained from a document. Does not authorize payment.
    """
    originals = {"po": po_bytes, "grn": grn_bytes, "invoice": invoice_bytes}
    identities = {}
    if not isinstance(attestations, Mapping) or not isinstance(trusted_keys, Mapping):
        return _bad("missing trusted signing configuration")
    for kind in KINDS:
        proof = attestations.get(kind)
        keys = trusted_keys.get(kind)
        if not isinstance(proof, dict) or not isinstance(keys, Mapping):
            return _bad(f"{kind}: missing role-scoped attestation")
        if set(proof) != {"actor_id", "mac"}:
            return _bad(f"{kind}: invalid attestation shape")
        actor_id = proof["actor_id"]
        signature = proof["mac"]
        if not isinstance(actor_id, str) or not actor_id.strip() or not isinstance(signature, str):
            return _bad(f"{kind}: invalid attestation")
        key = keys.get(actor_id)
        if not isinstance(key, bytes) or len(key) < 32:
            return _bad(f"{kind}: signer not provisioned for this role")
        if len(signature) != 64 or any(c not in "0123456789abcdef" for c in signature):
            return _bad(f"{kind}: malformed MAC")
        try:
            expected = source_mac(kind, originals[kind], key)
        except ValueError:
            return _bad(f"{kind}: invalid original bytes")
        if not hmac.compare_digest(signature, expected):
            return _bad(f"{kind}: source content or attestation mismatch")
        identities[kind] = actor_id

    # Separate keys prevent a caller from pretending three different roles.
    keys_in_use = [trusted_keys[kind][identities[kind]] for kind in KINDS]
    if len(set(keys_in_use)) != len(KINDS):
        return _bad("signing roles must not share a secret")
    report = audit_json_sources(po_bytes, grn_bytes, invoice_bytes)
    if report["status"] == UNVERIFIABLE:
        report["source_authenticity"] = "attested_but_data_unverifiable"
        report["attestors"] = identities
        return report
    report["source_authenticity"] = "role_scoped_hmac_attested"
    report["attestors"] = identities
    report["approval"] = False
    return report
