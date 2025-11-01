"""Minimal response primitives for the FastAPI compatibility shim."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

__all__ = [
    "Response",
    "JSONResponse",
    "HTMLResponse",
    "PlainTextResponse",
    "RedirectResponse",
    "FileResponse",
]


class Response:
    """Base HTTP response."""

    media_type = "text/plain"

    def __init__(
        self,
        content: Any = "",
        *,
        status_code: int = 200,
        headers: Dict[str, str] | None = None,
    ) -> None:
        self.content = content
        self.status_code = status_code
        self.headers = dict(headers or {})
        self.headers.setdefault("content-type", self.media_type)

    def render(self) -> Any:
        return self.content


class JSONResponse(Response):
    media_type = "application/json"

    def render(self) -> str:
        return json.dumps(self.content)


class HTMLResponse(Response):
    media_type = "text/html"

    def render(self) -> str:
        return str(self.content)


class PlainTextResponse(Response):
    media_type = "text/plain"

    def render(self) -> str:
        return str(self.content)


class RedirectResponse(Response):
    media_type = "text/plain"

    def __init__(
        self,
        url: str,
        *,
        status_code: int = 307,
        headers: Dict[str, str] | None = None,
    ) -> None:
        hdrs = dict(headers or {})
        hdrs.setdefault("location", url)
        super().__init__("", status_code=status_code, headers=hdrs)


class FileResponse(Response):
    media_type = "application/octet-stream"

    def __init__(
        self,
        path: str,
        *,
        filename: str | None = None,
        status_code: int = 200,
        headers: Dict[str, str] | None = None,
    ) -> None:
        data = Path(path).read_bytes()
        hdrs = dict(headers or {})
        if filename:
            hdrs.setdefault("content-disposition", f'attachment; filename="{filename}"')
        super().__init__(data, status_code=status_code, headers=hdrs)

    def render(self) -> bytes:
        return bytes(self.content)
