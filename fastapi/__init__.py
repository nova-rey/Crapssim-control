"""The real FastAPI package is preferred, but the project only relies on a very
small surface area for its HTTP command tests. This shim provides enough to
exercise the queueing logic without external dependencies."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Dict, Tuple

__all__ = ["FastAPI", "Request", "JSONResponse"]


class JSONResponse:
    """Minimal response carrying JSON content and status code."""

    def __init__(self, content: Any, status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code


class Request:
    """Simple request wrapper exposing an async ``json`` method."""

    def __init__(self, payload: Any) -> None:
        self._payload = payload

    async def json(self) -> Any:  # pragma: no cover - trivial async wrapper
        return self._payload


class FastAPI:
    """Tiny router that stores handlers for HTTP verbs."""

    def __init__(self) -> None:
        self._routes: Dict[Tuple[str, str], Callable[..., Any]] = {}
        self.router: Dict[str, Any] = {}

    def post(self, path: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        method = "POST"

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._routes[(method, path)] = func
            return func

        return decorator

    def get(self, path: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        method = "GET"

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._routes[(method, path)] = func
            return func

        return decorator

    def _dispatch(self, method: str, path: str, payload: Any) -> Tuple[int, Any]:
        handler = self._routes.get((method.upper(), path))
        if handler is None:
            raise ValueError(f"No route registered for {method} {path}")
        request = Request(payload)
        result = handler(request)
        if asyncio.iscoroutine(result):
            result = asyncio.run(result)
        if isinstance(result, JSONResponse):
            return result.status_code, result.content
        if isinstance(result, tuple) and len(result) == 2:
            status, body = result
            return int(status), body
        return 200, result

    async def __call__(self, scope: Dict[str, Any], receive: Callable[[], Any], send: Callable[[Dict[str, Any]], Any]) -> None:
        """Minimal ASGI entrypoint compatible with uvicorn."""

        if scope.get("type") != "http":
            await send(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b"Unsupported scope type",
                }
            )
            return

        method = scope.get("method", "GET")
        path = scope.get("path", "/")

        body_bytes = b""
        if method.upper() in {"POST", "PUT", "PATCH"}:
            while True:
                message = await receive()
                body_bytes += message.get("body", b"")
                if not message.get("more_body"):
                    break

        payload: Any = None
        if body_bytes:
            try:
                payload = json.loads(body_bytes.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload = body_bytes

        try:
            status, content = self._dispatch(method, path, payload)
        except ValueError:
            await send(
                {
                    "type": "http.response.start",
                    "status": 404,
                    "headers": [(b"content-type", b"text/plain")],
                }
            )
            await send({"type": "http.response.body", "body": b"Not Found"})
            return
        if not isinstance(content, (str, bytes)):
            content = json.dumps(content).encode("utf-8")
        elif isinstance(content, str):
            content = content.encode("utf-8")

        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": content})


from .testclient import TestClient  # noqa: E402,F401

__all__.append("TestClient")
