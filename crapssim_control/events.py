# crapssim_control/events.py
from __future__ import annotations
from typing import Dict, Any, Optional, Tuple

POINT_NUMS = {4, 5, 6, 8, 9, 10}
CRAPS_NUMS = {2, 3, 12}
NATURAL_NUMS = {7, 11}


def _as_tuple3(x: Any) -> Tuple[int, int, int]:
    """Return (d1, d2, total) or (0,0,int(x)) if not a proper dice tuple."""
    if isinstance(x, tuple) and len(x) >= 3:
        return int(x[0]), int(x[1]), int(x[2])
    try:
        tot = int(x)  # allow a single total
    except Exception:
        tot = 0
    return 0, 0, tot


def _normalize_state(s: Any) -> Dict[str, Any]:
    """
    Accept either:
      - dict-like with keys: comeout, total, point_on, point_num, just_est
      - GameState object with:
          s.table.comeout, s.table.dice -> (d1,d2,total),
          s.table.point_on, s.table.point_number,
          s.just_established_point
    and return a uniform dict.
    """
    if hasattr(s, "table"):
        t = getattr(s, "table", None)
        comeout = bool(getattr(t, "comeout", False))
        d1, d2, total = _as_tuple3(getattr(t, "dice", (0, 0, 0)))
        point_on = bool(getattr(t, "point_on", False))
        point_num = getattr(t, "point_number", None)
        just_est = bool(
            getattr(s, "just_established_point", False) or getattr(s, "just_est", False)
        )
        return {
            "comeout": comeout,
            "total": int(total),
            "point_on": point_on,
            "point_num": point_num,
            "just_est": just_est,
        }

    if isinstance(s, dict):
        total = int(s.get("total", 0))
        return {
            "comeout": bool(s.get("comeout", False)),
            "total": total,
            "point_on": bool(s.get("point_on", False)),
            "point_num": s.get("point_num"),
            "just_est": bool(s.get("just_est", False)),
        }

    return {"comeout": False, "total": 0, "point_on": False, "point_num": None, "just_est": False}


def derive_event(prev: Any, curr: Any) -> Dict[str, Any]:
    """
    Derive a semantic event from previous and current game state snapshots.

    Returns a dict with:
      - 'event'  : str (primary key expected by tests)
      - 'type'   : str (alias for backward compatibility)
      - 'roll'   : int (the current total)
      - 'point'  : Optional[int] (current point number if on)
      - 'natural': bool (only meaningful on comeout)
      - 'craps'  : bool (only meaningful on comeout)
    """
    c = _normalize_state(curr)

    roll: int = int(c["total"])
    comeout: bool = bool(c["comeout"])
    point_on: bool = bool(c["point_on"])
    point_num: Optional[int] = c["point_num"]
    just_est: bool = bool(c["just_est"])

    natural = False
    craps = False

    # Priority: if the roll *just established* the point, surface that first.
    if just_est:
        evt = "point_established"
    else:
        if comeout:
            # Comeout, not establishing a point: classify natural/craps/comeout
            if roll in NATURAL_NUMS:
                natural = True
                evt = "comeout"
            elif roll in CRAPS_NUMS:
                craps = True
                evt = "comeout"
            elif roll in POINT_NUMS:
                # If we get here it's an establishment without the just_est flag,
                # but still treat it as point_established for safety.
                evt = "point_established"
            else:
                evt = "comeout"
        else:
            # Point is on (or off) mid-hand
            if point_on and point_num is not None and roll == point_num:
                evt = "point_made"
            elif roll == 7:
                evt = "seven_out"
            else:
                evt = "roll"

    return {
        "event": evt,
        "type": evt,  # alias
        "roll": roll,
        "point": point_num if point_on else None,
        "natural": natural,
        "craps": craps,
    }