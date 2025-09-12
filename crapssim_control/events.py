# crapssim_control/events.py
from __future__ import annotations
from typing import Dict, Any, Optional, Tuple

POINT_NUMS = {4, 5, 6, 8, 9, 10}
CRAPS_NUMS = {2, 3, 12}
NATURAL_NUMS = {7, 11}


def _as_tuple3(x: Any) -> Tuple[int, int, int]:
    if isinstance(x, tuple) and len(x) >= 3:
        return int(x[0]), int(x[1]), int(x[2])
    try:
        return 0, 0, int(x)
    except Exception:
        return 0, 0, 0


def _normalize_state(s: Any) -> Dict[str, Any]:
    """
    Accept either:
      - dict-like with keys: comeout, total, point_on, point_num, just_est, just_made
      - GameState object with attributes on .table and flags like
        .just_established_point / .just_made_point
    """
    if hasattr(s, "table"):
        t = getattr(s, "table", None)
        comeout = bool(getattr(t, "comeout", False))
        _, _, total = _as_tuple3(getattr(t, "dice", (0, 0, 0)))
        point_on = bool(getattr(t, "point_on", False))
        point_num = getattr(t, "point_number", None)
        just_est = bool(
            getattr(s, "just_established_point", False) or getattr(s, "just_est", False)
        )
        just_made = bool(
            getattr(s, "just_made_point", False) or getattr(s, "just_made", False)
        )
        return {
            "comeout": comeout,
            "total": int(total),
            "point_on": point_on,
            "point_num": point_num,
            "just_est": just_est,
            "just_made": just_made,
        }

    if isinstance(s, dict):
        return {
            "comeout": bool(s.get("comeout", False)),
            "total": int(s.get("total", 0)),
            "point_on": bool(s.get("point_on", False)),
            "point_num": s.get("point_num"),
            "just_est": bool(s.get("just_est", False)),
            "just_made": bool(s.get("just_made", False)),
        }

    return {
        "comeout": False,
        "total": 0,
        "point_on": False,
        "point_num": None,
        "just_est": False,
        "just_made": False,
    }


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
    just_made: bool = bool(c["just_made"])

    natural = False
    craps = False

    # Priority of semantic events:
    # 1) point just established
    # 2) point just made
    # 3) comeout classifications / seven-out / generic roll
    if just_est:
        evt = "point_established"
    elif just_made:
        evt = "point_made"
    else:
        if comeout:
            if roll in NATURAL_NUMS:
                natural = True
                evt = "comeout"
            elif roll in CRAPS_NUMS:
                craps = True
                evt = "comeout"
            elif roll in POINT_NUMS:
                # Defensive: if upstream forgot to set just_est on establishment
                evt = "point_established"
            else:
                evt = "comeout"
        else:
            if point_on and point_num is not None and roll == point_num:
                evt = "point_made"
            elif roll == 7:
                evt = "seven_out"
            else:
                evt = "roll"

    return {
        "event": evt,
        "type": evt,  # alias for compatibility
        "roll": roll,
        "point": point_num if point_on else None,
        "natural": natural,
        "craps": craps,
    }