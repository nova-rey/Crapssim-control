from __future__ import annotations
from typing import Any, Dict, Optional


def _get(obj: Any, key: str, default=None):
    """Safely read attribute or dict key."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def derive_event(prev: Optional[Dict[str, Any]], curr: Dict[str, Any]) -> Dict[str, Any]:
    """
    Turn raw table snapshots into a simple event dict consumed by the rules engine.

    Priority/contract (matches tests):
      1) If a point is *just* established on a comeout roll -> {"event": "point_established"}
      2) Else if transitioning into comeout (or first snapshot on comeout) -> {"event": "comeout"}
      3) Otherwise -> {"event": "roll"}
    """
    # Normalize reads so we accept dicts or GameState-like objects.
    curr_comeout = bool(_get(curr, "comeout", False))
    curr_point = _get(curr, "point_number")
    curr_just_est = bool(_get(curr, "just_established_point", False))

    if prev is None:
        # First observation
        if curr_just_est:
            return {"event": "point_established", "point": curr_point}
        return {"event": "comeout"} if curr_comeout else {"event": "roll"}

    # Point establishment takes priority
    if curr_just_est:
        return {"event": "point_established", "point": curr_point}

    # Any time we are on comeout, emit comeout (tests expect this)
    if curr_comeout:
        return {"event": "comeout"}

    # Default neutral roll tick
    return {"event": "roll"}