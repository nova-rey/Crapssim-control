"""Compatibility-focused FastAPI shim with minimal routing support."""

from __future__ import annotations

import asyncio
import inspect
import json
import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from .responses import JSONResponse, Response

__all__ = ["FastAPI", "APIRouter", "Request", "JSONResponse", "Form"]


def _normalize_path(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return path


def _compile_path(path: str) -> Tuple[re.Pattern[str], Tuple[str, ...]]:
    path = _normalize_path(path)
    if path == "/":
        return re.compile(r"^/$"), tuple()
    parts = []
    names: List[str] = []
    for segment in path.strip("/").split("/"):
        if segment.startswith("{") and segment.endswith("}"):
            name = segment[1:-1]
            names.append(name)
            parts.append(rf"(?P<{name}>[^/]+)")
        else:
            parts.append(re.escape(segment))
    pattern = re.compile(r"^/" + "/".join(parts) + r"/?$")
    return pattern, tuple(names)


@dataclass
class _Route:
    method: str
    path: str
    endpoint: Callable[..., Any]
    pattern: re.Pattern[str]
    param_names: Tuple[str, ...]


class Request:
    """Simple request wrapper providing async ``json`` and ``app`` access."""

    def __init__(self, payload: Any, app: "FastAPI", path_params: Dict[str, str]):
        self._payload = payload
        self.app = app
        self.state = app.state
        self.path_params = path_params

    async def json(self) -> Any:  # pragma: no cover - async helper
        return self._payload


class _BaseRouter:
    def __init__(self) -> None:
        self._routes: List[_Route] = []

    def add_api_route(
        self,
        path: str,
        endpoint: Callable[..., Any],
        *,
        methods: Iterable[str] = ("GET",),
    ) -> None:
        for method in methods:
            normalized = _normalize_path(path)
            pattern, names = _compile_path(normalized)
            self._routes.append(
                _Route(method.upper(), normalized, endpoint, pattern, names)
            )

    def get(self, path: str, **_: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.add_api_route(path, func, methods=("GET",))
            return func

        return decorator

    def post(self, path: str, **_: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.add_api_route(path, func, methods=("POST",))
            return func

        return decorator


class APIRouter(_BaseRouter):
    pass


class FastAPI(_BaseRouter):
    def __init__(self, *args: Any, **kwargs: Any) -> None:  # signature compatible
        super().__init__()
        self.state = SimpleNamespace()
        self.router: Dict[str, Any] = {}
        self.title = kwargs.get("title", "FastAPI")
        self.version = kwargs.get("version", "0")
        self._mounts: List[Tuple[str, Any]] = []

    def include_router(
        self,
        router: APIRouter,
        *,
        prefix: str = "",
        tags: Optional[List[str]] = None,
    ) -> None:  # pragma: no cover - thin wrapper
        del tags  # unused in shim
        prefix_norm = _normalize_path(prefix) if prefix else ""
        for route in router._routes:
            full_path = _normalize_path(
                f"{prefix_norm}/{route.path.lstrip('/') if route.path != '/' else ''}"
            )
            self.add_api_route(full_path, route.endpoint, methods=(route.method,))

    def mount(self, path: str, app: Any, name: str | None = None) -> None:  # pragma: no cover
        self._mounts.append((path, app))
        if name:
            self.router[name] = app

    def _dispatch(self, method: str, path: str, payload: Any) -> Tuple[int, Any, Dict[str, str]]:
        method = method.upper()
        path = _normalize_path(path)
        for route in self._routes:
            if route.method != method:
                continue
            match = route.pattern.match(path)
            if not match:
                continue
            params = match.groupdict()
            request = Request(payload, self, params)
            kwargs = _extract_kwargs(route.endpoint, params, request)
            result = route.endpoint(**kwargs)
            if asyncio.iscoroutine(result):
                result = asyncio.run(result)
            return _finalize_response(result)
        raise ValueError(f"No route registered for {method} {path}")

    async def __call__(self, scope: Dict[str, Any], receive: Callable[[], Any], send: Callable[[Dict[str, Any]], Any]) -> None:
        if scope.get("type") != "http":  # pragma: no cover - basic guard
            await send({"type": "http.response.start", "status": 500, "headers": []})
            await send({"type": "http.response.body", "body": b"Unsupported scope type"})
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
            status, content, headers = self._dispatch(method, path, payload)
        except ValueError:
            await send(
                {"type": "http.response.start", "status": 404, "headers": [(b"content-type", b"text/plain")]}
            )
            await send({"type": "http.response.body", "body": b"Not Found"})
            return

        if isinstance(content, (dict, list)):
            body = json.dumps(content).encode("utf-8")
        elif isinstance(content, bytes):
            body = content
        else:
            body = str(content).encode("utf-8")

        header_items = [(k.encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()]
        if not any(k.lower() == b"content-type" for k, _ in header_items):
            header_items.append((b"content-type", b"text/plain"))

        await send({"type": "http.response.start", "status": status, "headers": header_items})
        await send({"type": "http.response.body", "body": body})


def _extract_kwargs(
    endpoint: Callable[..., Any], params: Dict[str, str], request: Request
) -> Dict[str, Any]:
    signature = inspect.signature(endpoint)
    kwargs: Dict[str, Any] = {}
    for name, param in signature.parameters.items():
        if name in {"request", "req"} or param.annotation is Request:
            kwargs[name] = request
        elif name in params:
            kwargs[name] = params[name]
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            kwargs[name] = params
    return kwargs


def _finalize_response(result: Any) -> Tuple[int, Any, Dict[str, str]]:
    headers: Dict[str, str] = {}
    if isinstance(result, Response):
        return result.status_code, result.render(), result.headers
    if isinstance(result, tuple):
        if len(result) == 3:
            status, body, headers = result
            return int(status), body, dict(headers)
        if len(result) == 2:
            status, body = result
            return int(status), body, headers
    if isinstance(result, (str, bytes, dict, list, int, float)):
        if isinstance(result, (dict, list)):
            headers["content-type"] = "application/json"
        return 200, result, headers
    return 200, json.loads(json.dumps(result)), headers


def Form(default: Any = ..., **_: Any) -> Any:  # pragma: no cover - placeholder
    return default


from .testclient import TestClient  # noqa: E402  # re-export for convenience

__all__.append("TestClient")
