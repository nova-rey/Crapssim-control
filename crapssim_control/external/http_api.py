"""
Minimal HTTP /commands endpoint with stdlib http.server.
If FASTAPI is available, create_app() returns a FastAPI app. Otherwise,
serve_commands() starts a stdlib server.
"""
from typing import Any, Dict, Callable, Tuple
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
def create_app(queue: CommandQueue, active_run_id_supplier: Callable[[], str]):
    try:
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
    except Exception:
        return None

    app = FastAPI()

    @app.post("/commands")
    async def post_commands(req: Request):
        body = await req.json()
        code, payload = ingest_command(body, queue, active_run_id_supplier)
        return JSONResponse(payload, status_code=code)

    return app


# Stdlib server (fallback)
def serve_commands(queue: CommandQueue, active_run_id_supplier: Callable[[], str], host="127.0.0.1", port=8089):
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/commands":
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            try:
                data = json.loads(body)
            except Exception:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"status":"rejected","reason":"bad_json"}')
                return
            code, payload = ingest_command(data, queue, active_run_id_supplier)
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))

    httpd = HTTPServer((host, port), Handler)
    return httpd  # caller decides threading/lifecycle
