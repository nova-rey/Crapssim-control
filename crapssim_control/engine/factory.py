"""Factory helpers for constructing engine adapters."""

from __future__ import annotations

import os
from typing import Any, Mapping

from ..engine_adapter import NullAdapter, VanillaAdapter
from .base import EngineAdapter
from .http_api_adapter import HttpEngineAdapter


def _coerce_timeout(value: Any, default: float = 10.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def build_engine_adapter(
    run_block: Mapping[str, Any] | None,
    *,
    http_client: Any | None = None,
) -> EngineAdapter:
    """Return an engine adapter instance for the requested run configuration."""

    config = run_block or {}
    engine_value = config.get("engine")
    engine_name = None
    if engine_value is not None:
        engine_name = str(engine_value).strip().lower()

    if not engine_name:
        return VanillaAdapter()

    if engine_name in {"null", "noop"}:
        return NullAdapter()

    if engine_name in {"inprocess", "vanilla"}:
        return VanillaAdapter()

    if engine_name == "http_api":
        http_cfg = config.get("engine_http")
        if not isinstance(http_cfg, Mapping):
            http_cfg = {}
        base_url = http_cfg.get("base_url")
        if not isinstance(base_url, str) or not base_url.strip():
            base_url = os.environ.get("CRAPSSIM_API_URL", "http://localhost:8000")
        timeout = _coerce_timeout(http_cfg.get("timeout_seconds"))
        return HttpEngineAdapter(base_url=base_url, timeout_seconds=timeout, client=http_client)

    raise ValueError(f"unknown engine '{engine_value}'")
