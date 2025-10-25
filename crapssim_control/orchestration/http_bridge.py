from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from queue import Empty
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

from .control_surface import ControlSurface, RunStatus
from .event_bus import EventBus


class _Handler(BaseHTTPRequestHandler):
    surface: ControlSurface | None = None
    bus: EventBus | None = None

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        # Silence default stderr logging to keep bridge quiet by default.
        pass

    def _json(self, code: int, payload: Dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/status":
            params = parse_qs(parsed.query)
            run_id = (params.get("id") or [None])[0]
            if not run_id:
                self._json(400, {"error": "missing id"})
                return
            try:
                status: RunStatus = self.surface.status(run_id)  # type: ignore[union-attr]
            except KeyError:
                self._json(404, {"error": "unknown run"})
                return
            self._json(
                200,
                {
                    "run_id": status.run_id,
                    "state": status.state,
                    "started_at": status.started_at,
                    "finished_at": status.finished_at,
                    "artifacts_dir": status.artifacts_dir,
                    "error": status.error,
                },
            )
        elif parsed.path == "/events":
            sid, queue = self.bus.subscribe()  # type: ignore[union-attr]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                while True:
                    if getattr(self.server, "_BaseServer__shutdown_request", False):
                        break
                    try:
                        event = queue.get(timeout=0.25)
                    except Empty:
                        if getattr(self.wfile, "closed", False):
                            break
                        continue
                    try:
                        self.wfile.write(self.bus.to_sse(event))  # type: ignore[union-attr]
                        self.wfile.flush()
                    except BrokenPipeError:
                        break
            finally:
                self.bus.unsubscribe(sid)  # type: ignore[union-attr]
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except Exception:
            self._json(400, {"error": "invalid json"})
            return

        if parsed.path == "/run/start":
            spec = payload.get("spec") or {}
            run_root = payload.get("run_root") or ""
            run_id = self.surface.launch(spec, run_root)  # type: ignore[union-attr]
            self._json(200, {"run_id": run_id})
        elif parsed.path == "/run/stop":
            run_id = payload.get("run_id")
            if not run_id:
                self._json(400, {"error": "missing run_id"})
                return
            ok = self.surface.stop(run_id)  # type: ignore[union-attr]
            self._json(200, {"ok": ok})
        else:
            self._json(404, {"error": "not found"})


def serve(host: str, port: int, surface: ControlSurface, bus: EventBus) -> HTTPServer:
    _Handler.surface = surface
    _Handler.bus = bus
    server = HTTPServer((host, port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
