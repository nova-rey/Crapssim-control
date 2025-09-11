from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Optional


def _dice_total(snapshot: Dict[str, Any]) -> Optional[int]:
    """
    Read total from a snapshot shaped like {"table":{"dice":(d1,d2,total), ...}}
    """
    tbl = (snapshot or {}).get("table", {}) or {}
    dice = tbl.get("dice")
    if isinstance(dice, (list, tuple)) and len(dice) == 3:
        try:
            return int(dice[2])
        except Exception:
            return None
    return None


class Tracker:
    """
    Lightweight tracker used by tests:
      - on_roll(total)
      - on_point_established(point)
      - snapshot() -> dict including ["roll"]["last_roll"] and ["point"]["point"]
      - observe(prev, curr, event) exists (used internally)

    We intentionally keep behavior minimal to satisfy current tests.
    """

    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        self.config = config or {}
        # counters
        self.total_rolls: int = 0
        self.comeout_rolls: int = 0
        self.point_phase_rolls: int = 0
        self.hits_by_total = defaultdict(int)
        self.points_established: int = 0
        self.points_made: int = 0
        self.seven_outs: int = 0

        # state
        self.current_point: Optional[int] = None
        self.last_total: Optional[int] = None
        self.last_event: Optional[str] = None

        # snapshots
        self._prev_snapshot: Optional[Dict[str, Any]] = None
        self._curr_snapshot: Optional[Dict[str, Any]] = None

    # --- API the tests call ---------------------------------------------------

    def on_roll(self, total: int) -> None:
        comeout = self.current_point is None
        curr = {
            "table": {
                "dice": (0, 0, int(total)),
                "comeout": comeout,
                "point_on": (self.current_point is not None),
                "point_number": self.current_point,
                # roll_index isn't required for this test; omit or set 1
                "roll_index": 1 if self.current_point is not None else 0,
            }
        }
        self.observe(self._curr_snapshot, curr, {"event": "roll"})

    def on_point_established(self, point: int) -> None:
        # Transition to point-on phase
        self.current_point = int(point)
        self.points_established += 1
        curr = {
            "table": {
                "dice": (0, 0, int(point)),
                "comeout": False,
                "point_on": True,
                "point_number": self.current_point,
                "roll_index": 1,
            }
        }
        self.observe(self._curr_snapshot, curr, {"event": "point_established"})

    def snapshot(self) -> Dict[str, Any]:
        # Provide both the nested shape expected by tests and flat counters for convenience
        return {
            "roll": {"last_roll": self.last_total},
            "point": {"point": self.current_point, "current": self.current_point},
            "totals": dict(self.hits_by_total),
            "total_rolls": self.total_rolls,
            "comeout_rolls": self.comeout_rolls,
            "point_phase_rolls": self.point_phase_rolls,
            "points_established": self.points_established,
            "points_made": self.points_made,
            "seven_outs": self.seven_outs,
            "current_point": self.current_point,
            "last_total": self.last_total,
            "last_event": self.last_event,
        }

    # --- Internal -------------------------------------------------------------

    def observe(self, prev: Any, curr: Any, event: Optional[Dict[str, Any]] = None) -> None:
        self._prev_snapshot = prev
        self._curr_snapshot = curr

        ev_name = (event or {}).get("event")
        self.last_event = ev_name

        total = _dice_total(curr)
        if total is not None and 2 <= total <= 12:
            self.last_total = total
            self.hits_by_total[total] += 1

        self.total_rolls += 1

        tbl = (curr or {}).get("table", {}) or {}
        if tbl.get("comeout"):
            self.comeout_rolls += 1
        else:
            self.point_phase_rolls += 1