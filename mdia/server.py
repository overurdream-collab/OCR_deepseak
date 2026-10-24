"""Dependency-free local HTTP API + web UI (stdlib only; binds to 127.0.0.1 by default).

POST /api/upload?filename=x.pdf[&ocr=auto|force|off]   body = raw PDF bytes  -> {job_id}
GET  /api/jobs | /api/jobs/{id} | /api/jobs/{id}/result | /api/jobs/{id}/pdf | /api/jobs/{id}/pages/{n}.png
POST /api/jobs/{id}/reprocess     {"ocr":"force"}
POST /api/jobs/{id}/corrections   {"record_id","field","value","note"}      (raw document is never modified)
DELETE /api/jobs/{id}/corrections?record_id=..&field=..     DELETE /api/jobs/{id}
GET  /api/jobs/{id}/export?format=json|csv|xlsx|pdf         GET /api/schema | /api/health
"""
import json
import mimetypes
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import config, exporters
from .pipeline import process_job
from .reader import available_ocr_langs
from .store import Store

STATIC = Path(__file__).parent / "static"
SCHEMA = config.ROOT / "schema" / "mdia.schema.json"
POOL = ThreadPoolExecutor(max_workers=config.WORKERS)
STORE = Store()
_JOB = re.compile(r"^/api/jobs/([0-9a-f]{12})(?:/(.*))?$")


def submit(job_id, ocr="auto"):
    POOL.submit(process_job, STORE, job_id, ocr if ocr in ("auto", "force", "off") else "auto")


def resume_unfinished():
    for j in STORE.list():
        if j.get("state") in ("queued", "processing"):
            submit(j["job_id"], j.get("ocr_mode", "auto"))   # per-page cache makes this cheap


class Handler(BaseHTTPRequestHandler):
    server_version = "MDIA/1.0"

    def log_message(self, fmt, *a):          # never log URLs/filenames of medical files
        pass

    # ---- helpers
    def _send(self, code, body=b"", ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _auth(self):
        if not config.API_TOKEN:
            return True
        q = parse_qs(urlparse(self.path).query)
        tok = self.headers.get("Authorization", "").replace("Bearer ", "") or (q.get("token") or [""])[0]
        if tok == config.API_TOKEN:
            return True
        self._send(401, {"error": "unauthorized"})
        return False

    def _json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    # ---- routing
    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if not self._auth():
            return
        try:
            if u.path == "/api/health":
                return self._send(200, {"ok": True, "ocr_languages": sorted(available_ocr_langs()), "workers": config.WORKERS,
                                        "arabic_pdf_font": str(exporters.find_arabic_font())})
            if u.path == "/api/schema":
                return self._send(200, SCHEMA.read_bytes())
            if u.path == "/api/jobs":
                return self._send(200, STORE.list())
            m = _JOB.match(u.path)
            if not m:
                return self._send(404, {"error": "not found"})
            jid, rest = m.group(1), m.group(2) or ""
            if rest == "":
                return self._send(200, {"job_id": jid, **STORE.status(jid)})
            if rest == "result":
                r = STORE.result(jid)
                return self._send(200, r) if r else self._send(409, {"error": "result not ready", **STORE.status(jid)})
            if rest == "pdf":
                return self._send(200, STORE.path(jid, "original.pdf").read_bytes(), "application/pdf")
            pm = re.fullmatch(r"pages/(\d+)\.png", rest)
            if pm:
                return self._send(200, STORE.path(jid, "pages", f"{int(pm.group(1))}.png").read_bytes(), "image/png")
            if rest == "export":
                fmt = (parse_qs(u.query).get("format") or ["json"])[0]
                r = STORE.result(jid)
                if not r:
                    return self._send(409, {"error": "result not ready"})
                ext = {"json": ("application/json", exporters.to_json), "csv": ("application/zip", exporters.to_csv_zip),
                       "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", exporters.to_xlsx),
                       "pdf": ("application/pdf", exporters.to_pdf)}.get(fmt)
                if not ext:
                    return self._send(400, {"error": "format must be json|csv|xlsx|pdf"})
                name = "mdia_" + jid + (".zip" if fmt == "csv" else "." + fmt)
                try:
                    body = ext[1](r)
                except exporters.PdfExportError as e:
                    return self._send(500, {"error": str(e)})
                return self._send(200, body, ext[0], {"Content-Disposition": f'attachment; filename="{name}"'})
            return self._send(404, {"error": "not found"})
        except KeyError:
            return self._send(404, {"error": "job not found"})
        except FileNotFoundError:
            return self._send(404, {"error": "file not found"})

    def do_POST(self):
        if not self._auth():
            return
        u = urlparse(self.path)
        try:
            if u.path == "/api/upload":
                q = parse_qs(u.query)
                n = int(self.headers.get("Content-Length") or 0)
                if n > config.MAX_UPLOAD_MB * 1024 * 1024:
                    return self._send(413, {"error": f"max {config.MAX_UPLOAD_MB} MB"})
                body = self.rfile.read(n)
                jid = STORE.create((q.get("filename") or ["document.pdf"])[0], body)
                ocr = (q.get("ocr") or ["auto"])[0]
                STORE.set_status(jid, ocr_mode=ocr)
                submit(jid, ocr)
                return self._send(202, {"job_id": jid})
            m = _JOB.match(u.path)
            if m and m.group(2) == "reprocess":
                jid = m.group(1)
                ocr = self._json().get("ocr", "auto")
                STORE.status(jid)
                submit(jid, ocr)
                return self._send(202, {"job_id": jid, "state": "queued"})
            if m and m.group(2) == "corrections":
                b = self._json()
                if not all(k in b for k in ("record_id", "field", "value")):
                    return self._send(400, {"error": "record_id, field, value required"})
                STORE.add_correction(m.group(1), b["record_id"], b["field"], b["value"], b.get("note", ""))
                return self._send(200, {"ok": True})
            return self._send(404, {"error": "not found"})
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        except KeyError:
            return self._send(404, {"error": "job not found"})

    def do_DELETE(self):
        if not self._auth():
            return
        u = urlparse(self.path)
        m = _JOB.match(u.path)
        try:
            if m and m.group(2) == "corrections":
                q = parse_qs(u.query)
                STORE.delete_correction(m.group(1), q["record_id"][0], q["field"][0])
                return self._send(200, {"ok": True})
            if m and not m.group(2):
                STORE.delete_job(m.group(1))
                return self._send(200, {"ok": True})
        except (KeyError, IndexError):
            return self._send(404, {"error": "not found"})
        return self._send(404, {"error": "not found"})


def make_server(host=None, port=None):
    return ThreadingHTTPServer((host or config.HOST, port if port is not None else config.PORT), Handler)


def main():
    resume_unfinished()
    srv = make_server()
    print(f"MDIA running on http://{config.HOST}:{config.PORT}  (data: {config.DATA_DIR})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
