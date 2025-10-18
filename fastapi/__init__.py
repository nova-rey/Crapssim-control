"""Lightweight FastAPI compatibility layer for test environments.

The real FastAPI package is preferred, but the project only relies on a very
small surface area for its HTTP command tests.  This shim provides enough to
exercise the queueing logic without external dependencies.
"""

from __future__ import annotations

import asyncio
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

    def post(self, path: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        method = "POST"

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


from .testclient import TestClient  # noqa: E402

__all__.append("TestClient")
