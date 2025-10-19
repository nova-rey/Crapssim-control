"""
Minimal HTTP /commands endpoint with stdlib http.server.
If FASTAPI is available, create_app() returns a FastAPI app. Otherwise,
serve_commands() starts a stdlib server.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple
import asyncio
import json
import logging
import threading
import time
from urllib import error as urllib_error
from urllib import request as urllib_request
from pathlib import Path

from .command_channel import CommandQueue, ALLOWED_ACTIONS
from crapssim_control.engine_adapter import VerbRegistry, PolicyRegistry


logger = logging.getLogger("CSC.HTTP")


def get_capabilities() -> Dict[str, Any]:
    verbs = sorted(list(VerbRegistry._handlers.keys()))
    policies = sorted(list(PolicyRegistry._handlers.keys()))
    return {
        "effect_schema": "1.0",
        "verbs": verbs,
        "policies": policies,
    }


def _load_snapshot_tag(snapshot_path: Optional[str | Path] = None) -> Optional[str]:
    path: Path
    if snapshot_path is None:
        try:
            path = Path(__file__).resolve().parents[2] / "docs" / "CSC_SNAPSHOT.yaml"
        except Exception:
            return None
    else:
        try:
            path = Path(snapshot_path)
        except Exception:
            return None
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("tag:"):
            _, _, value = line.partition(":")
            val = value.strip().strip('"').strip("'")
            if val:
                return val
    return None

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
    tag_supplier: Optional[Callable[[], str]] = None,
):
    try:
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
    except Exception:
        return

    if not isinstance(app, FastAPI):
        return

    @app.get("/health")
    def health(_request=None):
        return JSONResponse({"status": "ok"})

    @app.get("/run_id")
    def run_id(_request=None):
        rid = active_run_id_supplier() or ""
        return JSONResponse({"run_id": rid})

    @app.get("/version")
    def version(_request=None):
        version_value = "unknown"
        build_hash_value = "unknown"
        tag_value = "unknown"
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
        if callable(tag_supplier):
            try:
                tag_val = tag_supplier()
            except Exception:
                tag_val = None
            if isinstance(tag_val, str) and tag_val:
                tag_value = tag_val
        if tag_value == "unknown":
            snapshot_tag = _load_snapshot_tag()
            if isinstance(snapshot_tag, str) and snapshot_tag:
                tag_value = snapshot_tag
        return JSONResponse({"version": version_value, "build_hash": build_hash_value, "tag": tag_value})


def create_app(
    queue: CommandQueue,
    active_run_id_supplier: Callable[[], str],
    *,
    version_supplier: Optional[Callable[[], str]] = None,
    build_hash_supplier: Optional[Callable[[], str]] = None,
    tag_supplier: Optional[Callable[[], str]] = None,
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
        tag_supplier=tag_supplier,
    )

    @app.get("/capabilities")
    def capabilities():
        return get_capabilities()

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
    tag_supplier: Optional[Callable[[], str]] = None,
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
                tag_value = "unknown"
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
                if callable(tag_supplier):
                    try:
                        tval = tag_supplier()
                    except Exception:
                        tval = None
                    if isinstance(tval, str) and tval:
                        tag_value = tval
                if tag_value == "unknown":
                    snapshot_tag = _load_snapshot_tag()
                    if isinstance(snapshot_tag, str) and snapshot_tag:
                        tag_value = snapshot_tag
                self._write_json(
                    200,
                    {"version": version_value, "build_hash": build_hash_value, "tag": tag_value},
                )
                return
            if self.path == "/capabilities":
                self._write_json(200, get_capabilities())
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


class HTTPServerHandle:
    """Simple lifecycle wrapper for whichever HTTP server is active."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._thread: Optional[threading.Thread] = None
        self._httpd = None
        self._uvicorn_server = None
        self._uvicorn_loop: Optional[asyncio.AbstractEventLoop] = None
        self._using_uvicorn = False
        self._stopped = False

    @property
    def using_uvicorn(self) -> bool:
        return self._using_uvicorn

    def _start_uvicorn(
        self,
        app,
        *,
        log_level: str = "warning",
    ) -> None:
        import uvicorn

        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level=log_level,
            lifespan="auto",
        )
        server = uvicorn.Server(config)
        server.install_signal_handlers = lambda: None  # type: ignore[assignment]

        loop_ready = threading.Event()
        exc_holder: list[BaseException] = []

        def _runner() -> None:
            loop = asyncio.new_event_loop()
            self._uvicorn_loop = loop
            asyncio.set_event_loop(loop)
            loop_ready.set()
            try:
                loop.run_until_complete(server.serve())
            except BaseException as exc:  # noqa: BLE001
                exc_holder.append(exc)
            finally:
                try:
                    loop.close()
                finally:
                    self._uvicorn_loop = None

        thread = threading.Thread(
            target=_runner,
            name="csc-external-api",
            daemon=True,
        )
        thread.start()
        loop_ready.wait(timeout=1.0)
        time.sleep(0.05)
        if exc_holder:
            thread.join(timeout=1.0)
            raise exc_holder[0]
        if not thread.is_alive():
            thread.join(timeout=1.0)
            raise RuntimeError("uvicorn server exited during startup")
        self._thread = thread
        self._uvicorn_server = server
        self._using_uvicorn = True

    def _start_stdlib(
        self,
        queue: CommandQueue,
        active_run_id_supplier: Callable[[], str],
        *,
        version_supplier: Optional[Callable[[], str]] = None,
        build_hash_supplier: Optional[Callable[[], str]] = None,
        tag_supplier: Optional[Callable[[], str]] = None,
    ) -> None:
        httpd = serve_commands(
            queue,
            active_run_id_supplier,
            host=self.host,
            port=self.port,
            version_supplier=version_supplier,
            build_hash_supplier=build_hash_supplier,
            tag_supplier=tag_supplier,
        )
        actual_host, actual_port = httpd.server_address
        self.host = str(actual_host)
        self.port = int(actual_port)
        thread = threading.Thread(
            target=httpd.serve_forever,
            name="csc-external-httpd",
            daemon=True,
        )
        thread.start()
        self._thread = thread
        self._httpd = httpd
        self._using_uvicorn = False

    def stop(self) -> None:
        if self._stopped:
            return
        try:
            if self._using_uvicorn and self._uvicorn_server is not None:
                self._uvicorn_server.should_exit = True
                self._uvicorn_server.force_exit = True
                loop = self._uvicorn_loop
                if loop is not None:
                    loop.call_soon_threadsafe(lambda: None)
                self._uvicorn_server = None
            elif self._httpd is not None:
                self._httpd.shutdown()
                self._httpd.server_close()
                self._httpd = None
            if self._thread is not None and self._thread.is_alive():
                self._thread.join(timeout=2.0)
            self._thread = None
        finally:
            self._stopped = True
            logger.info("[CSC.HTTP] server stopped")

    def _probe_health(self) -> None:
        time.sleep(0.1)
        url = f"http://{self.host}:{self.port}/health"
        try:
            with urllib_request.urlopen(url, timeout=2.0) as resp:
                status = resp.getcode()
        except urllib_error.URLError as exc:
            logger.error(
                "[CSC.HTTP] health probe failed: %s: %s for %s",
                exc.__class__.__name__,
                getattr(exc, "reason", exc),
                url,
            )
            return
        if status != 200:
            logger.error("[CSC.HTTP] health=%s for %s", status, url)
        else:
            logger.info("[CSC.HTTP] health=200 for %s:%s", self.host, self.port)


def start_http_server(
    queue: CommandQueue,
    active_run_id_supplier: Callable[[], str],
    *,
    host: str = "127.0.0.1",
    port: int = 8089,
    version_supplier: Optional[Callable[[], str]] = None,
    build_hash_supplier: Optional[Callable[[], str]] = None,
    tag_supplier: Optional[Callable[[], str]] = None,
) -> HTTPServerHandle:
    handle = HTTPServerHandle(host, port)
    app = create_app(
        queue,
        active_run_id_supplier,
        version_supplier=version_supplier,
        build_hash_supplier=build_hash_supplier,
        tag_supplier=tag_supplier,
    )

    if app is not None:
        try:
            handle._start_uvicorn(app)
        except BaseException as exc:  # noqa: BLE001
            logger.warning(
                "[CSC.HTTP] uvicorn failed: %s: %s (%s:%s). Falling back to stdlib server.",
                exc.__class__.__name__,
                exc,
                host,
                port,
            )
        else:
            handle._probe_health()
            return handle

    handle._start_stdlib(
        queue,
        active_run_id_supplier,
        version_supplier=version_supplier,
        build_hash_supplier=build_hash_supplier,
        tag_supplier=tag_supplier,
    )
    logger.info("[CSC.HTTP] running stdlib HTTP on %s:%s", handle.host, handle.port)
    handle._probe_health()
    return handle
