"""Minimal TestClient for the FastAPI compatibility shim."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import FastAPI


@dataclass
class _Response:
    status_code: int
    payload: Any

    def json(self) -> Any:
        return self.payload


class TestClient:
    def __init__(self, app: FastAPI) -> None:
        self.app = app

    def post(self, path: str, json: Any | None = None, **_: Any) -> _Response:
        status, payload = self.app._dispatch("POST", path, json or {})
        return _Response(status_code=status, payload=payload)

    def get(self, path: str, params: Any | None = None, **_: Any) -> _Response:
        status, payload = self.app._dispatch("GET", path, params or {})
        return _Response(status_code=status, payload=payload)
