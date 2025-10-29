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
    """Coerce a loosely-typed flag value into ``True``/``False``/``None``.

    ``default`` is returned when ``value`` is ``None`` or explicitly requests
    inheritance (``"default"``/``"auto"``). The boolean in the return tuple
    indicates whether the coercion succeeded.
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


def get_journal_options(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Extract journal explain options from the run spec."""

    run_blk = (spec or {}).get("run") if isinstance(spec, dict) else {}
    journal_blk = run_blk.get("journal") if isinstance(run_blk, dict) else {}
    journal: Dict[str, Any] = journal_blk if isinstance(journal_blk, dict) else {}
    explain_enabled = bool(journal.get("explain", False))
    grouping = journal.get("explain_grouping") or "first_only"
    return {
        "explain": explain_enabled,
        "explain_grouping": grouping,
    }


def get_policy_options(spec: Dict[str, Any]) -> Dict[str, Any]:
    run = (spec or {}).get("run") or {}
    pol = run.get("policy") or {}
    return {
        "enforce": bool(pol.get("enforce", True)),
        "report": bool(pol.get("report", False)),
    }


def get_stop_options(spec: Dict[str, Any]) -> Dict[str, Any]:
    run = (spec or {}).get("run") or {}
    return {
        "stop_on_bankrupt": bool(run.get("stop_on_bankrupt", True)),
        "stop_on_unactionable": bool(run.get("stop_on_unactionable", True)),
    }


def get_table_mins(spec: Dict[str, Any]) -> Dict[str, Any]:
    run = (spec or {}).get("run") or {}
    mins = run.get("table_mins") or {}
    # Defaults
    place_unit = mins.get("place_unit") or {}
    return {
        "line": float(mins.get("line", 5)),
        "field": float(mins.get("field", 5)),
        "odds_unit": float(mins.get("odds_unit", 5)),
        "place_unit": {
            "default": float(place_unit.get("default", 5)),
            "4": float(place_unit.get("4", place_unit.get("default", 5))),
            "5": float(place_unit.get("5", place_unit.get("default", 5))),
            "6": float(place_unit.get("6", place_unit.get("default", 6))),
            "8": float(place_unit.get("8", place_unit.get("default", 6))),
            "9": float(place_unit.get("9", place_unit.get("default", 5))),
            "10": float(place_unit.get("10", place_unit.get("default", 5))),
        },
    }
