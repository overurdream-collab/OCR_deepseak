"""Local SQLite replay registry and append-only hash-chain for *audit events*.

Not a general ledger or payment system. Requires role-attested structured
sources. SQLite file access and an external hash-chain anchor are operational
security responsibilities; this module cannot make a compromised OS trustworthy.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from .attestation import audit_attested_sources
from .core import UNVERIFIABLE
from .source import parse_structured_json


def _blocked(reason):
    return {"status": UNVERIFIABLE, "approval": False,
            "findings": [], "reasons": [reason],
            "source_authenticity": "blocked", "ruleset": "invoice-audit-v0.1"}


class AuditRegistry:
    def __init__(self, database: str | Path):
        self.database = str(database)
        if self.database == ":memory:":
            raise ValueError("in-memory registry cannot guarantee replay protection across connections")
        self._create()

    def _connect(self):
        con = sqlite3.connect(self.database, timeout=10, isolation_level=None)
        con.execute("PRAGMA busy_timeout=10000")
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def _create(self):
        with self._connect() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS audit_events(
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant TEXT NOT NULL,
                supplier TEXT NOT NULL,
                invoice_id TEXT NOT NULL,
                invoice_sha256 TEXT NOT NULL,
                result_json TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL,
                UNIQUE(tenant, supplier, invoice_id)
            )""")

    @staticmethod
    def _hash_event(previous, payload):
        return hashlib.sha256((previous + "\n" + payload).encode("utf-8")).hexdigest()

    def audit_once(self, tenant_id, po_bytes, grn_bytes, invoice_bytes,
                   attestations, trusted_keys):
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            return _blocked("missing tenant identifier")
        report = audit_attested_sources(
            po_bytes, grn_bytes, invoice_bytes, attestations, trusted_keys)
        if report["status"] == UNVERIFIABLE:
            return report
        try:
            invoice = parse_structured_json(invoice_bytes, "invoice")
        except ValueError as exc:
            return _blocked(str(exc))
        supplier = invoice["supplier_id"]["value"]
        invoice_id = invoice["document_id"]["value"]
        invoice_hash = hashlib.sha256(invoice_bytes).hexdigest()
        try:
            with self._connect() as con:
                con.execute("BEGIN IMMEDIATE")
                existing = con.execute(
                    "SELECT invoice_sha256 FROM audit_events WHERE tenant=? AND supplier=? AND invoice_id=?",
                    (tenant_id, supplier, invoice_id)).fetchone()
                if existing:
                    con.rollback()
                    return _blocked("duplicate invoice identifier previously audited; correction workflow required")
                row = con.execute(
                    "SELECT event_hash FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
                prev = row[0] if row else "0" * 64
                payload = json.dumps({
                    "tenant": tenant_id, "supplier": supplier,
                    "invoice_id": invoice_id, "invoice_sha256": invoice_hash,
                    "report": report}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                digest = self._hash_event(prev, payload)
                con.execute(
                    """INSERT INTO audit_events
                       (tenant, supplier, invoice_id, invoice_sha256,
                        result_json, previous_hash, event_hash)
                       VALUES (?,?,?,?,?,?,?)""",
                    (tenant_id, supplier, invoice_id, invoice_hash, payload, prev, digest))
                con.commit()
        except sqlite3.Error:
            return _blocked("audit registry unavailable; fail closed")
        return {**report, "event_hash": digest, "approval": False,
                "replay_protected": True}

    def verify_chain(self) -> bool:
        """Checks event hash continuity, not independent protection from DB rewrites."""
        try:
            with self._connect() as con:
                rows = con.execute(
                    "SELECT tenant,supplier,invoice_id,invoice_sha256,result_json,previous_hash,event_hash "
                    "FROM audit_events ORDER BY seq").fetchall()
        except sqlite3.Error:
            return False
        prev = "0" * 64
        for tenant, supplier, invoice_id, invoice_hash, payload, prior, digest in rows:
            if prior != prev or self._hash_event(prev, payload) != digest:
                return False
            try:
                obj = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                return False
            if (obj.get("tenant"), obj.get("supplier"), obj.get("invoice_id"),
                obj.get("invoice_sha256")) != (tenant, supplier, invoice_id, invoice_hash):
                return False
            prev = digest
        return True
