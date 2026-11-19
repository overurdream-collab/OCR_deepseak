"""Role scoped source attestation negative and tamper tests."""
import copy
import unittest

from invoice_audit.attestation import audit_attested_sources, source_mac
from invoice_audit import MATCH, UNVERIFIABLE
from tests.test_invoice_audit_source import payload, blob


class AttestationTests(unittest.TestCase):
    def setUp(self):
        self.data = {k: blob(payload(k)) for k in ("po", "grn", "invoice")}
        self.secrets = {k: bytes([index]) * 32
                        for index, k in enumerate(("po", "grn", "invoice"), 1)}
        self.keys = {k: {f"{k}-actor": secret} for k, secret in self.secrets.items()}
        self.proofs = {k: {"actor_id": f"{k}-actor",
                           "mac": source_mac(k, self.data[k], self.secrets[k])}
                       for k in self.data}

    def check(self, expected):
        r = audit_attested_sources(self.data["po"], self.data["grn"],
                                   self.data["invoice"], self.proofs, self.keys)
        self.assertEqual(r["status"], expected, r)
        self.assertFalse(r["approval"])
        return r

    def test_valid_independent_attestation(self):
        result = self.check(MATCH)
        self.assertEqual(result["source_authenticity"], "role_scoped_hmac_attested")

    def test_tampered_invoice_fails(self):
        self.data["invoice"] += b" "
        self.check(UNVERIFIABLE)

    def test_wrong_role_key_fails(self):
        self.keys["invoice"] = self.keys["po"]
        self.check(UNVERIFIABLE)

    def test_unknown_actor_fails(self):
        self.proofs["po"]["actor_id"] = "stranger"
        self.check(UNVERIFIABLE)

    def test_missing_attestation_fails(self):
        del self.proofs["grn"]
        self.check(UNVERIFIABLE)

    def test_wrong_kind_signature_fails(self):
        self.proofs["po"]["mac"] = source_mac("invoice", self.data["po"], self.secrets["po"])
        self.check(UNVERIFIABLE)

    def test_invalid_mac_format_fails(self):
        self.proofs["po"]["mac"] = "invalid"
        self.check(UNVERIFIABLE)

    def test_shared_secret_across_roles_fails(self):
        same = bytes([9]) * 32
        self.secrets = {k: same for k in self.secrets}
        self.keys = {k: {f"{k}-actor": same} for k in self.secrets}
        self.proofs = {k: {"actor_id": f"{k}-actor", "mac": source_mac(k, self.data[k], same)}
                       for k in self.data}
        self.check(UNVERIFIABLE)

    def test_valid_mac_but_invalid_financial_reference_fails(self):
        d = payload("invoice")
        d["po_reference"] = "different-order"
        self.data["invoice"] = blob(d)
        self.proofs["invoice"]["mac"] = source_mac(
            "invoice", self.data["invoice"], self.secrets["invoice"])
        report = self.check(UNVERIFIABLE)
        self.assertEqual(report["source_authenticity"], "attested_but_data_unverifiable")


if __name__ == "__main__":
    unittest.main()
