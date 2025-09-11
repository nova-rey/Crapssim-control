from __future__ import annotations
from typing import Any, Dict, Optional


def _get(obj: Any, key: str, default=None):
    """Safely read attribute or dict key."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _get_comeout(snapshot: Any) -> bool:
    """
    Some snapshots carry comeout on the top-level, others nest it under table.
    Be tolerant to both shapes used in tests.
    """
    v = _get(snapshot, "comeout", None)
    if v is not None:
        return bool(v)
    table = _get(snapshot, "table", None)
    return bool(_get(table, "comeout", False))


def derive_event(prev: Optional[Dict[str, Any]], curr: Dict[str, Any]) -> Dict[str, Any]:
    """
    Turn raw table snapshots into a simple event dict consumed by the rules engine.

    Priority/contract (matches tests):
      1) If a point is *just* established on a comeout roll -> {"event": "point_established"}
      2) If a point was *just* made (seven off the point or hit the point) -> {"event": "point_made"}
      3) Else if currently on comeout -> {"event": "comeout"}
      4) Otherwise -> {"event": "roll"}
    """
    curr_just_est = bool(_get(curr, "just_established_point", False))
    curr_just_made = bool(_get(curr, "just_made_point", False))
    curr_point = _get(curr, "point_number", None)
    curr_comeout = _get_comeout(curr)

    if prev is None:
        if curr_just_est:
            return {"event": "point_established", "point": curr_point}
        if curr_just_made:
            return {"event": "point_made"}
        return {"event": "comeout"} if curr_comeout else {"event": "roll"}

    # Point establishment takes priority
    if curr_just_est:
        return {"event": "point_established", "point": curr_point}

    # Point made (e.g., roll returned to comeout with just_made flag)
    if curr_just_made:
        return {"event": "point_made"}

    # Any time we are on comeout, emit comeout (tests expect this)
    if curr_comeout:
        return {"event": "comeout"}

    # Default neutral roll tick
    return {"event": "roll"}