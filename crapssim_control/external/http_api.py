"""
Minimal HTTP /commands endpoint with stdlib http.server.
If FASTAPI is available, create_app() returns a FastAPI app. Otherwise,
serve_commands() starts a stdlib server.
"""
from typing import Any, Callable, Dict, Optional, Tuple
import json

from .command_channel import CommandQueue, ALLOWED_ACTIONS

def ingest_command(body: Dict[str, Any], queue: CommandQueue, active_run_id_supplier: Callable[[], str]) -> Tuple[int, Dict[str, Any]]:
    rid = body.get("run_id")
    if not rid or rid != active_run_id_supplier():
        return 400, {"status": "rejected", "reason": "run_id_mismatch"}
    if body.get("action") not in ALLOWED_ACTIONS:
        return 400, {"status": "rejected", "reason": "unknown_action"}
    ok, reason = queue.enqueue(body)
    if not ok:
        return 400, {"status": "rejected", "reason": reason}
    return 202, {"status": "queued"}


# Optional FastAPI surface (used if dependency exists)
def register_diagnostics(
    app,
    active_run_id_supplier: Callable[[], str],
    version_supplier: Optional[Callable[[], str]] = None,
    build_hash_supplier: Optional[Callable[[], str]] = None,
):
    try:
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
    except Exception:
        return

    if not isinstance(app, FastAPI):
        return

    @app.get("/health")
    async def health(_request=None):
        return JSONResponse({"status": "ok"})

    @app.get("/run_id")
    async def run_id(_request=None):
        rid = active_run_id_supplier() or ""
        return JSONResponse({"run_id": rid})

    @app.get("/version")
    async def version(_request=None):
        version_value = "unknown"
        build_hash_value = "unknown"
        if callable(version_supplier):
            try:
                value = version_supplier()
            except Exception:
                value = None
            if isinstance(value, str) and value:
                version_value = value
        if callable(build_hash_supplier):
            try:
                build_val = build_hash_supplier()
            except Exception:
                build_val = None
            if isinstance(build_val, str) and build_val:
                build_hash_value = build_val
        return JSONResponse({"version": version_value, "build_hash": build_hash_value})


def create_app(
    queue: CommandQueue,
    active_run_id_supplier: Callable[[], str],
    *,
    version_supplier: Optional[Callable[[], str]] = None,
    build_hash_supplier: Optional[Callable[[], str]] = None,
):
    try:
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
    except Exception:
        return None

    app = FastAPI()
    if not callable(getattr(app, "__call__", None)) or not hasattr(app, "router"):
        return None

    register_diagnostics(
        app,
        active_run_id_supplier,
        version_supplier=version_supplier,
        build_hash_supplier=build_hash_supplier,
    )

    @app.post("/commands")
    async def post_commands(req: Request):
        body = await req.json()
        code, payload = ingest_command(body, queue, active_run_id_supplier)
        return JSONResponse(payload, status_code=code)

    return app


# Stdlib server (fallback)
def serve_commands(
    queue: CommandQueue,
    active_run_id_supplier: Callable[[], str],
    host="127.0.0.1",
    port=8089,
    *,
    version_supplier: Optional[Callable[[], str]] = None,
    build_hash_supplier: Optional[Callable[[], str]] = None,
):
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def _write_json(self, code: int, payload: Dict[str, Any]) -> None:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))

        def do_GET(self):
            if self.path == "/health":
                self._write_json(200, {"status": "ok"})
                return
            if self.path == "/run_id":
                rid = active_run_id_supplier() or ""
                self._write_json(200, {"run_id": rid})
                return
            if self.path == "/version":
                version_value = "unknown"
                build_hash_value = "unknown"
                if callable(version_supplier):
                    try:
                        val = version_supplier()
                    except Exception:
                        val = None
                    if isinstance(val, str) and val:
                        version_value = val
                if callable(build_hash_supplier):
                    try:
                        bval = build_hash_supplier()
                    except Exception:
                        bval = None
                    if isinstance(bval, str) and bval:
                        build_hash_value = bval
                self._write_json(200, {"version": version_value, "build_hash": build_hash_value})
                return
            self._write_json(404, {"status": "not_found"})

        def do_POST(self):
            if self.path != "/commands":
                self._write_json(404, {"status": "not_found"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            try:
                data = json.loads(body)
            except Exception:
                self._write_json(400, {"status": "rejected", "reason": "missing:payload"})
                return
            code, payload = ingest_command(data, queue, active_run_id_supplier)
            self._write_json(code, payload)

    httpd = HTTPServer((host, port), Handler)
    return httpd  # caller decides threading/lifecycle
