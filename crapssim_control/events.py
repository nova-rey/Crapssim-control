# crapssim_control/events.py
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

__all__ = ["capture_table_state", "derive_event"]


def capture_table_state(table: Any) -> Dict[str, Any]:
    """
    Take a lightweight snapshot of the engine/table needed to derive high-level events.

    We intentionally keep this minimal so it works with both the real CrapsSim
    engine and the fake/shim tables used in tests.

    Expected attributes if present:
      - table.point: int | None (None/0 means no point established)
      - table.last_roll: tuple[int, int] | None (e.g., (3,4))
    """
    point = getattr(table, "point", None)
    if point in (0, False):
        point = None

    last_roll: Optional[Tuple[int, int]] = getattr(table, "last_roll", None)
    # Some engines store total only; accept that too.
    if isinstance(last_roll, int):
        last_roll = (last_roll, 0)  # sentinel second die

    state: Dict[str, Any] = {
        "point": point,
        "comeout": point is None,
        "last_roll": last_roll,
    }
    return state


def derive_event(prev: Optional[Dict[str, Any]], curr: Dict[str, Any]) -> Dict[str, Any]:
    """
    Turn raw table snapshots into a simple event dict consumed by the rules engine.

    Contract:
      - Must at least emit {"event": "comeout"} when transitioning to come-out
      - Otherwise emit a neutral tick event: {"event": "tick"}

    We keep this conservative--specific bet resolution events are raised elsewhere
    by the engine/adapter and fed into the rules runner directly.
    """
    if prev is None:
        # First observation: if we're on comeout, signal it so strategies can stage.
        return {"event": "comeout"} if curr.get("comeout") else {"event": "tick"}

    was_comeout = bool(prev.get("comeout"))
    is_comeout = bool(curr.get("comeout"))

    if not was_comeout and is_comeout:
        return {"event": "comeout"}

    # Fallback neutral event
    return {"event": "tick"}