# crapssim_control/events.py
from __future__ import annotations
from typing import Dict, Any, Optional


POINT_NUMS = {4, 5, 6, 8, 9, 10}
CRAPS_NUMS = {2, 3, 12}
NATURAL_NUMS = {7, 11}


def _bool(x: Any) -> bool:
    return bool(x)


def derive_event(prev: Dict[str, Any], curr: Dict[str, Any]) -> Dict[str, Any]:
    """
    Derive a semantic event from previous and current game state snapshots.

    Both `prev` and `curr` are dict-like objects with (at least) these keys:
      - 'comeout' : bool        -> whether the roll is a comeout roll
      - 'total'   : int         -> the dice total for the current roll
      - 'point_on': bool        -> whether a point is currently on (after roll)
      - 'point_num': Optional[int] -> the current point number if on, else None
      - 'just_est': Optional[bool]  -> True if this roll just established the point

    Returns a dict with:
      - 'event'  : str (primary key expected by tests)
      - 'type'   : str (alias for backward compatibility)
      - 'roll'   : int (the current total)
      - 'point'  : Optional[int] (current point number if on)
      - 'natural': bool (only meaningful on comeout)
      - 'craps'  : bool (only meaningful on comeout)
    """
    # Pull with safe defaults to tolerate slightly different shapes
    roll: int = int(curr.get("total", 0))
    comeout: bool = _bool(curr.get("comeout", False))
    point_on: bool = _bool(curr.get("point_on", False))
    point_num: Optional[int] = curr.get("point_num")
    just_est: bool = _bool(curr.get("just_est", False))

    natural = False
    craps = False

    # Decide primary event
    if comeout:
        # Priority: if this roll establishes a point, tests accept "point_established"
        # even when the number is a point number (4,5,6,8,9,10).
        if roll in POINT_NUMS or just_est:
            evt = "point_established"
        else:
            # Otherwise it’s a generic "comeout" event, with flags for natural/craps.
            if roll in NATURAL_NUMS:
                natural = True
            elif roll in CRAPS_NUMS:
                craps = True
            evt = "comeout"
    else:
        # Point is already on or we're in the box numbers phase
        if point_on and point_num is not None and roll == point_num:
            evt = "point_made"
        elif roll == 7:
            # Seven when point is on is a seven-out; even if point_on is false due to
            # upstream timing, 7 without comeout is a seven-out for our purposes.
            evt = "seven_out"
        else:
            evt = "roll"

    event: Dict[str, Any] = {
        "event": evt,     # tests read this
        "type": evt,      # compatibility alias
        "roll": roll,
        "point": point_num if point_on else None,
        "natural": natural,
        "craps": craps,
    }
    return event