# crapssim_control/events.py
from typing import Optional, Dict, Any
from .snapshotter import GameState

def _pass_result(prev: Optional[GameState], curr: GameState) -> Optional[str]:
    """Return 'win'/'lose'/None for Pass Line on this roll."""
    total = curr.table.dice[2] if curr.table.dice else None
    if total is None:
        return None
    # Come-out: point is OFF for this roll
    if curr.table.comeout:
        if total in (7, 11):
            return "win"
        if total in (2, 3, 12):
            return "lose"
        return None  # establishing a point → no resolution yet
    # Point ON: win by hitting point, lose on 7-out
    if prev and prev.table.point_on:
        if total == prev.table.point_number:
            return "win"
        if total == 7:
            return "lose"
    return None

def _dp_result(prev: Optional[GameState], curr: GameState) -> Optional[str]:
    """Return 'win'/'lose'/None for Don't Pass (assume bar-12 push)."""
    total = curr.table.dice[2] if curr.table.dice else None
    if total is None:
        return None
    # Come-out
    if curr.table.comeout:
        if total in (2, 3):
            return "win"
        if total in (7, 11):
            return "lose"
        if total == 12:
            return None  # push
        return None
    # Point ON
    if prev and prev.table.point_on:
        if total == 7:
            return "win"
        if total == prev.table.point_number:
            return "lose"
    return None

def derive_event(prev: Optional[GameState], curr: GameState) -> Dict[str, Any]:
    """
    v0.3 event derivation priority:
      1) bet_resolved (pass/dp) if a win/lose happened
      2) seven_out
      3) point_made
      4) point_established
      5) comeout  (fires on every comeout roll)
      6) roll     (always)
    """
    # Bet resolutions first so rules can react immediately
    p = _pass_result(prev, curr)
    if p in ("win", "lose"):
        return {"event": "bet_resolved", "bet": "pass", "result": p}

    dp = _dp_result(prev, curr)
    if dp in ("win", "lose"):
        return {"event": "bet_resolved", "bet": "dont_pass", "result": dp}

    if curr.just_seven_out:
        return {"event": "seven_out"}

    # Explicit point_made (separate from bet_resolved)
    if curr.just_made_point and prev is not None:
        return {"event": "point_made", "number": prev.table.point_number}

    if curr.just_established_point:
        return {"event": "point_established", "number": curr.table.point_number}

    # Explicit comeout event during the comeout phase
    if curr.table.comeout:
        return {"event": "comeout"}

    # Fallback generic roll
    total = curr.table.dice[2] if curr.table.dice else None
    return {"event": "roll", "total": total}

__all__ = ["derive_event"]