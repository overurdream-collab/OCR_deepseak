"""Thirty independently varied three-source acceptance cases (90 documents).

All data are synthetic and content/role-attested; the acceptance set is
not a proxy for real supplier invoices or OCR accuracy.
"""
import unittest
from invoice_audit.attestation import audit_attested_sources, source_mac
from invoice_audit import MATCH, EXCEPTION, UNVERIFIABLE
from tests.test_invoice_audit_source import payload, blob


class AcceptanceMatrixTests(unittest.TestCase):
    def test_thirty_triplets_no_silent_mismatch(self):
        counts = {"match": 0, "exception": 0, "unverifiable": 0}
        for scenario in range(30):
            with self.subTest(scenario=scenario):
                po, grn, inv = payload("po"), payload("grn"), payload("invoice")
                po["document_id"] = f"po-{scenario}"
                grn["document_id"] = f"grn-{scenario}"
                grn["po_reference"] = f"po-{scenario}"
                inv["document_id"] = f"invoice-{scenario}"
                inv["po_reference"] = f"po-{scenario}"
                inv["grn_reference"] = f"grn-{scenario}"
                expected = MATCH
                if scenario % 3 == 1:
                    grn["lines"][0]["quantity"] = str(9 - scenario // 10)
                    expected = EXCEPTION
                elif scenario % 3 == 2:
                    inv["lines"][0]["unit_price"] = str(6 + scenario // 10)
                    inv["lines"][0]["line_total"] = str(10 * (6 + scenario // 10))
                    inv["stated_total"] = inv["lines"][0]["line_total"]
                    expected = EXCEPTION
                if scenario in (8, 17, 26):
                    inv["currency"] = "SAR"
                    expected = UNVERIFIABLE
                docs = {"po": blob(po), "grn": blob(grn), "invoice": blob(inv)}
                keys = {kind: {f"{kind}-actor": bytes([index]) * 32}
                        for index, kind in enumerate(docs, 1)}
                proofs = {kind: {"actor_id": f"{kind}-actor",
                                 "mac": source_mac(kind, data, keys[kind][f"{kind}-actor"])}
                          for kind, data in docs.items()}
                actual = audit_attested_sources(
                    docs["po"], docs["grn"], docs["invoice"], proofs, keys)
                self.assertEqual(actual["status"], expected, actual)
                self.assertFalse(actual["approval"])
                self.assertNotEqual(actual.get("source_authenticity"), "failed")
                counts[{MATCH: "match", EXCEPTION: "exception",
                        UNVERIFIABLE: "unverifiable"}[expected]] += 1
        self.assertEqual(sum(counts.values()), 30)
        print("Acceptance matrix: 30 synthetic triplets / 90 source documents:", counts)


if __name__ == "__main__":
    unittest.main()
