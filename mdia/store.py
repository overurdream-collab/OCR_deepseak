"""Filesystem job store: private directories, atomic writes, corrections kept apart from raw results."""
import hashlib
import json
import os
import re
import secrets
import time
from pathlib import Path

from . import config


def _atomic_write(path: Path, data: bytes):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(path)


def safe_name(name: str) -> str:
    name = os.path.basename(name or "document.pdf")
    name = re.sub(r"[^\w.\- \u0600-\u06FF]", "_", name).strip(". ")[:120] or "document.pdf"
    return name if name.lower().endswith(".pdf") else name + ".pdf"


class Store:
    def __init__(self, root: Path = None):
        self.root = Path(root or config.DATA_DIR) / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass

    def _dir(self, job_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{12}", job_id):
            raise KeyError("bad job id")
        d = self.root / job_id
        if not d.is_dir():
            raise KeyError(job_id)
        return d

    def create(self, filename: str, content: bytes) -> str:
        if len(content) > config.MAX_UPLOAD_MB * 1024 * 1024:
            raise ValueError(f"file larger than {config.MAX_UPLOAD_MB} MB")
        if b"%PDF-" not in content[:1024]:
            raise ValueError("not a PDF file")
        job_id = secrets.token_hex(6)
        d = self.root / job_id
        d.mkdir(parents=True)
        _atomic_write(d / "original.pdf", content)
        self.set_status(job_id, state="queued", progress=0, filename=safe_name(filename),
                        sha256=hashlib.sha256(content).hexdigest(), created=time.time(), size=len(content))
        return job_id

    def path(self, job_id, *parts) -> Path:
        return self._dir(job_id).joinpath(*parts)

    def status(self, job_id) -> dict:
        return json.loads(self.path(job_id, "status.json").read_text("utf-8"))

    def set_status(self, job_id, **kw):
        d = self.root / job_id
        p = d / "status.json"
        cur = json.loads(p.read_text("utf-8")) if p.exists() else {}
        cur.update(kw)
        cur["updated"] = time.time()
        _atomic_write(p, json.dumps(cur, ensure_ascii=False).encode("utf-8"))

    def list(self):
        out = []
        for d in sorted(self.root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if (d / "status.json").exists():
                s = json.loads((d / "status.json").read_text("utf-8"))
                out.append({"job_id": d.name, **s})
        return out

    def save_result(self, job_id, result: dict):
        _atomic_write(self.path(job_id, "result.json"), json.dumps(result, ensure_ascii=False, indent=1).encode("utf-8"))

    def result(self, job_id, with_corrections=True):
        p = self.path(job_id, "result.json")
        if not p.exists():
            return None
        r = json.loads(p.read_text("utf-8"))
        return apply_corrections(r, self.corrections(job_id)) if with_corrections else r

    def corrections(self, job_id) -> dict:
        p = self.path(job_id, "corrections.json")
        return json.loads(p.read_text("utf-8")) if p.exists() else {}

    def add_correction(self, job_id, record_id, field, value, note=""):
        c = self.corrections(job_id)
        c[f"{record_id}|{field}"] = {"record_id": record_id, "field": field, "value": value, "note": note, "at": time.time()}
        _atomic_write(self.path(job_id, "corrections.json"), json.dumps(c, ensure_ascii=False, indent=1).encode("utf-8"))

    def delete_correction(self, job_id, record_id, field):
        c = self.corrections(job_id)
        c.pop(f"{record_id}|{field}", None)
        _atomic_write(self.path(job_id, "corrections.json"), json.dumps(c, ensure_ascii=False, indent=1).encode("utf-8"))

    def delete_job(self, job_id):
        import shutil
        shutil.rmtree(self._dir(job_id))


def apply_corrections(result: dict, corrections: dict) -> dict:
    """Overlay user corrections as `corrected_value`; raw and extracted values stay untouched."""
    if not corrections:
        return result
    import copy
    r = copy.deepcopy(result)
    for doc in r["documents"]:
        did = doc["document_id"]
        index = {f"{did}:patient": doc["patient"], f"{did}:provider": doc["provider"], f"{did}:hospitalization": doc["hospitalization"]}
        for key in ("invoices", "invoice_items", "medications", "diagnoses", "laboratory_tests", "imaging", "procedures"):
            for rec in doc[key]:
                index[rec["id"]] = rec
        done = set()
        for c in corrections.values():
            rec = index.get(c["record_id"])
            if rec is not None and c["field"] in rec and isinstance(rec[c["field"]], dict):
                f = rec[c["field"]]
                f["corrected_value"], f["verification"], f["correction_note"] = c["value"], "corrected", c.get("note", "")
                done.add((c["record_id"], c["field"]))
        doc["requires_human_review"] = [q for q in doc["requires_human_review"] if (q["record_id"], q["field"]) not in done]
    return r
