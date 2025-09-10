from typing import Optional, Dict, Any
from .snapshotter import GameState

def derive_event(prev: Optional[GameState], curr: GameState) -> Dict[str, Any]:
    """
    Minimal v0 event derivation.
    Priority: seven_out > point_established > roll
    """
    if curr.just_seven_out:
        return {"event": "seven_out"}
    if curr.just_established_point:
        return {"event": "point_established", "number": curr.table.point_number}
    total = curr.table.dice[2] if curr.table.dice else None
    return {"event": "roll", "total": total}