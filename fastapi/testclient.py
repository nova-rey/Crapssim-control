"""Minimal TestClient compatible with the FastAPI shim."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict

from . import FastAPI


@dataclass
class _Response:
    status_code: int
    content: Any
    headers: Dict[str, str]

    def json(self) -> Any:
        if isinstance(self.content, (bytes, bytearray)):
            data = self.content.decode("utf-8")
        else:
            data = self.content
        if isinstance(data, (dict, list)):
            return data
        return json.loads(data)

    @property
    def text(self) -> str:
        if isinstance(self.content, (bytes, bytearray)):
            return self.content.decode("utf-8")
        return str(self.content)


class TestClient:
    def __init__(self, app: FastAPI) -> None:
        self.app = app

    def post(
        self,
        path: str,
        json: Any | None = None,
        headers: Dict[str, str] | None = None,
        **_: Any,
    ) -> _Response:
        status, payload, headers_out = self.app._dispatch(
            "POST", path, json or {}, headers=headers or {}
        )
        return _Response(status_code=status, content=payload, headers=headers_out)

    def get(
        self,
        path: str,
        params: Any | None = None,
        headers: Dict[str, str] | None = None,
        **_: Any,
    ) -> _Response:
        status, payload, headers_out = self.app._dispatch(
            "GET", path, params or {}, headers=headers or {}
        )
        return _Response(status_code=status, content=payload, headers=headers_out)
