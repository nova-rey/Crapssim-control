"""Lightweight fallback for the :mod:`requests` library.

The project prefers the real ``requests`` package, but our tests and CLI
should remain usable in environments where it is unavailable.  The helper
below installs a minimal stub into :data:`sys.modules` so imports succeed.
The stub exposes a ``post`` function with a requests-like signature.  It is
sufficient for the webhook publisher tests, which monkeypatch the function
and never rely on actual network behaviour.
"""

from __future__ import annotations

import sys
import types
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional

__all__ = ["ensure_requests_module", "post", "RequestException", "Response"]


class RequestException(Exception):
    """Exception raised when the fallback HTTP request fails."""


@dataclass
class Response:
    """Minimal response object mirroring the real library."""

    status_code: int
    text: str

    def raise_for_status(self) -> None:
        if not (200 <= self.status_code < 400):
            raise RequestException(f"HTTP {self.status_code}: {self.text}")


def _coerce_data(data: Any, json_payload: Any) -> bytes:
    if json_payload is not None:
        import json as _json

        return _json.dumps(json_payload).encode("utf-8")
    if data is None:
        return b""
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        return data.encode("utf-8")
    return str(data).encode("utf-8")


def post(
    url: str,
    data: Any = None,
    json: Any = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
    **_: Any,
) -> Response:
    """Best-effort HTTP POST using :mod:`urllib`.

    Network failures raise :class:`RequestException`, mirroring ``requests``.
    ``headers`` defaults to an empty mapping.
    """

    payload = _coerce_data(data, json)
    request = urllib.request.Request(url, data=payload, method="POST")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
            return Response(status_code=response.getcode(), text=body)
    except urllib.error.URLError as exc:  # pragma: no cover - network failure
        raise RequestException(str(exc)) from exc


def ensure_requests_module() -> types.ModuleType:
    """Install the fallback stub into :data:`sys.modules` if needed."""

    module = sys.modules.get("requests")
    if module is not None:
        return module

    stub = types.ModuleType("requests")
    stub.post = post  # type: ignore[attr-defined]
    stub.RequestException = RequestException  # type: ignore[attr-defined]
    stub.Response = Response  # type: ignore[attr-defined]
    sys.modules["requests"] = stub
    return stub
