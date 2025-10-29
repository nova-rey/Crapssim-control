"""Compatibility helpers for optional third-party dependencies."""

from __future__ import annotations

__all__ = ["ensure_requests_module"]

from .requests_stub import ensure_requests_module
