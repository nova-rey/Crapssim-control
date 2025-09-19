from __future__ import annotations
from typing import Any, Dict, Tuple

def read_flags(spec: Dict[str, Any]) -> Tuple[bool, bool]:
    """
    Return (hot_table_enabled, guardrails_enabled) from spec.meta.flags.
    Defaults are False, False if not present.
    """
    meta = spec.get("meta", {}) or {}
    flags = meta.get("flags", {}) or {}
    hot = bool(flags.get("hot_table", False))
    grd = bool(flags.get("guardrails", False))
    return hot, grd

def ensure_meta_flags(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Make sure spec.meta.flags exists. Mutates and returns spec for convenience.
    """
    meta = spec.setdefault("meta", {})
    meta.setdefault("flags", {})
    return spec

def set_flag(spec: Dict[str, Any], name: str, value: bool) -> None:
    ensure_meta_flags(spec)
    spec["meta"]["flags"][name] = bool(value)