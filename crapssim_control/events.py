# crapssim_control/events.py
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple

__all__ = ["capture_table_state", "derive_event"]


def _from(obj: Any, *names: str) -> Any:
    """Best-effort getter that works for both dict-like and attribute objects.
    Tries top-level first, then looks under `.table` for each name.
    """
    for name in names:
        # direct
        if isinstance(obj, dict):
            if name in obj:
                return obj.get(name)
        else:
            if hasattr(obj, name):
                return getattr(obj, name)

        # under .table
        tbl = obj.get("table") if isinstance(obj, dict) else getattr(obj, "table", None)
        if tbl is not None:
            if isinstance(tbl, dict):
                if name in tbl:
                    return tbl.get(name)
            else:
                if hasattr(tbl, name):
                    return getattr(tbl, name)
    return None


def capture_table_state(table: Any) -> Dict[str, Any]:
    """Lightweight snapshot usable by derive_event(prev, curr)."""
    point = getattr(table, "point", None)
    if point in (0, False):
        point = None

    last_roll = getattr(table, "last_roll", None)
    if isinstance(last_roll, int):
        last_roll = (last_roll, 0)  # tolerate engines that store only total

    return {
        "point": point,
        "comeout": point is None,
        "last_roll": last_roll,
    }


def derive_event(prev: Optional[Any], curr: Any) -> Dict[str, Any]:
    """Translate raw state → high-level event for rules.

    Priority (highest first):
      1) seven_out
      2) point_made
      3) point_established
      4) comeout (transition into comeout)
      5) roll (neutral)
    Works with either our GameState objects or plain dict snapshots.
    """
    # Current flags
    just_seven_out = bool(_from(curr, "just_seven_out"))
    just_made_point = bool(_from(curr, "just_made_point"))
    just_est_point = bool(_from(curr, "just_established_point"))

    # Comeout flags
    curr_comeout = bool(_from(curr, "comeout"))
    prev_comeout = bool(_from(prev, "comeout")) if prev is not None else None

    # Point number (various engines use point_number or point)
    curr_point_num = _from(curr, "point_number", "point")

    if just_seven_out:
        return {"event": "seven_out"}
    if just_made_point:
        return {"event": "point_made"}
    if just_est_point:
        return {"event": "point_established", "point": curr_point_num}

    if prev is None:
        # first observation
        return {"event": "comeout"} if curr_comeout else {"event": "roll"}

    if prev_comeout is False and curr_comeout is True:
        return {"event": "comeout"}

    return {"event": "roll"}