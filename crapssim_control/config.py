"""Runtime configuration defaults and flag normalization helpers."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

DEMO_FALLBACKS_DEFAULT: bool = False
STRICT_DEFAULT: bool = False
EMBED_ANALYTICS_DEFAULT: bool = True

_TRUE_STRINGS = {"true", "1", "yes", "on"}
_FALSE_STRINGS = {"false", "0", "no", "off"}
_DEFAULT_STRINGS = {"default", "auto", "inherit"}


def coerce_flag(value: Any, *, default: Optional[bool] = None) -> Tuple[Optional[bool], bool]:
    """Best-effort coercion of flag-style inputs to bools.

    Returns ``(normalized_value, ok)`` where ``ok`` indicates whether the value
    could be interpreted. ``normalized_value`` falls back to ``default`` when
    the input is ``None`` or explicitly requests the default (``"default"`` or
    ``"auto"``). Unknown values yield ``ok=False``.
    """
    if isinstance(value, bool):
        return value, True
    if value is None:
        return default, True
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUE_STRINGS:
            return True, True
        if text in _FALSE_STRINGS:
            return False, True
        if default is not None and text in _DEFAULT_STRINGS:
            return default, True
        return None, False
    if isinstance(value, (int, float)):
        if value == 1:
            return True, True
        if value == 0:
            return False, True
        return None, False
    return None, False


def normalize_demo_fallbacks(run_blk: Optional[Dict[str, Any]]) -> bool:
    """Resolve ``run.demo_fallbacks`` honoring backwards-compatible inputs."""
    value = None
    if isinstance(run_blk, dict):
        value = run_blk.get("demo_fallbacks")
    normalized, ok = coerce_flag(value, default=DEMO_FALLBACKS_DEFAULT)
    if ok and normalized is not None:
        return bool(normalized)
    if ok and normalized is None:
        return DEMO_FALLBACKS_DEFAULT
    return DEMO_FALLBACKS_DEFAULT
