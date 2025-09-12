# crapssim_control/events.py
from __future__ import annotations
from typing import Dict, Any


def derive_event(roll: int, point: int | None) -> Dict[str, Any]:
    """
    Map a raw dice roll and point state into a semantic event dict.

    Returns:
        {
          "type": str,        # event category
          "roll": int,        # the rolled number
          "point": int|None,  # current point, if any
          "natural": bool,    # True if comeout natural (7 or 11)
          "craps": bool,      # True if comeout craps (2, 3, 12)
        }
    """
    event: Dict[str, Any] = {
        "roll": roll,
        "point": point,
        "natural": False,
        "craps": False,
    }

    if point is None:  # comeout roll
        if roll in (7, 11):
            event["type"] = "comeout_natural"
            event["natural"] = True
        elif roll in (2, 3, 12):
            event["type"] = "comeout_craps"
            event["craps"] = True
        else:
            event["type"] = "point_established"
    else:
        if roll == 7:
            event["type"] = "seven_out"
        elif roll == point:
            event["type"] = "point_made"
        else:
            event["type"] = "roll"

    return event