"""Audit registry replay protection / tamper evidence smoke tests."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from invoice_audit.registry import AuditRegistry
from invoice_audit.attestation import source_mac
from invoice_audit import MATCH, UNVERIFIABLE
from tests.test_invoice_audit_source import payload, blob


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "audit.db"
        self.registry = AuditRegistry(self.path)
        self.data = {k: blob(payload(k)) for k in ("po", "grn", "invoice")}
        self.keys = {k: {f"{k}-actor": bytes([n]) * 32}
                     for n, k in enumerate(("po", "grn", "invoice"), 1)}
        self.proofs = {k: {"actor_id": f"{k}-actor",
                           "mac": source_mac(k, self.data[k],
                                             self.keys[k][f"{k}-actor"])}
                       for k in self.data}

    def audit(self, tenant="t1"):
        return self.registry.audit_once(
            tenant, self.data["po"], self.data["grn"], self.data["invoice"],
            self.proofs, self.keys)

    def test_first_audit_stores_event_without_payment(self):
        out = self.audit()
        self.assertEqual(out["status"], MATCH, out)
        self.assertFalse(out["approval"])
        self.assertTrue(out["replay_protected"])
        self.assertTrue(self.registry.verify_chain())

    def test_duplicate_invoice_id_blocked(self):
        self.assertEqual(self.audit()["status"], MATCH)
        again = self.audit()
        self.assertEqual(again["status"], UNVERIFIABLE)
        self.assertIn("duplicate", again["reasons"][0])
        self.assertTrue(self.registry.verify_chain())

    def test_different_tenant_not_merged(self):
        self.assertEqual(self.audit("tenant-one")["status"], MATCH)
        self.assertEqual(self.audit("tenant-two")["status"], MATCH)
        self.assertTrue(self.registry.verify_chain())

    def test_changed_invoice_id_with_new_valid_attestation(self):
        self.assertEqual(self.audit()["status"], MATCH)
        inv = payload("invoice")
        inv["document_id"] = "new-id"
        self.data["invoice"] = blob(inv)
        self.proofs["invoice"]["mac"] = source_mac(
            "invoice", self.data["invoice"], self.keys["invoice"]["invoice-actor"])
        self.assertEqual(self.audit()["status"], MATCH)
        self.assertTrue(self.registry.verify_chain())

    def test_untrusted_mac_never_saved(self):
        self.proofs["invoice"]["mac"] = "0" * 64
        self.assertEqual(self.audit()["status"], UNVERIFIABLE)
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0], 0)

    def test_modified_history_detected(self):
        self.assertEqual(self.audit()["status"], MATCH)
        with sqlite3.connect(self.path) as con:
            con.execute("UPDATE audit_events SET result_json='tampered' WHERE seq=1")
        self.assertFalse(self.registry.verify_chain())

    def test_missing_tenant_rejected(self):
        self.assertEqual(self.audit("")["status"], UNVERIFIABLE)

    def test_inmemory_database_disallowed(self):
        with self.assertRaises(ValueError):
            AuditRegistry(":memory:")


if __name__ == "__main__":
    unittest.main()
