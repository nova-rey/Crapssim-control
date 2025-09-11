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
      - on_bankroll_delta(delta)
      - snapshot() -> dict including:
            ["roll"]["last_roll"]
            ["roll"]["rolls_since_point"]
            ["roll"]["shooter_rolls"]
            ["point"]["point"]
            ["hits"][total]  (frequency by total)
            ["bankroll"]["bankroll"]        (cumulative delta)
            ["bankroll"]["bankroll_peak"]   (max cumulative delta seen)
            ["bankroll"]["drawdown"]        (peak - current cum delta)
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
        self.rolls_since_point: Optional[int] = None  # None when no point is on
        self.last_bankroll_delta: float = 0.0
        self.cum_bankroll_delta: float = 0.0
        self.bankroll_peak: float = 0.0

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
                "roll_index": 1 if self.current_point is not None else 0,
            }
        }
        self.observe(self._curr_snapshot, curr, {"event": "roll"})

    def on_point_established(self, point: int) -> None:
        # Transition to point-on phase
        self.current_point = int(point)
        self.points_established += 1
        # reset rolls-since-point at the moment the point is established
        self.rolls_since_point = 0
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

    def on_bankroll_delta(self, delta: float) -> None:
        """Record a bankroll delta (some tests call this; used in snapshot)."""
        try:
            d = float(delta)
        except Exception:
            d = 0.0
        self.last_bankroll_delta = d
        self.cum_bankroll_delta += d
        # track peak for tests
        if self.cum_bankroll_delta > self.bankroll_peak:
            self.bankroll_peak = self.cum_bankroll_delta

    def snapshot(self) -> Dict[str, Any]:
        shooter_rolls = 0
        if self.current_point is not None:
            # Count the establishing roll as 1; subsequent rolls increment rolls_since_point.
            shooter_rolls = 1 + (self.rolls_since_point or 0)

        drawdown = max(0.0, self.bankroll_peak - self.cum_bankroll_delta)

        return {
            "roll": {
                "last_roll": self.last_total,
                "rolls_since_point": self.rolls_since_point if self.rolls_since_point is not None else 0,
                "shooter_rolls": shooter_rolls,
            },
            "point": {"point": self.current_point, "current": self.current_point},
            "hits": dict(self.hits_by_total),          # snap["hits"][8]
            "totals": dict(self.hits_by_total),        # keep prior key too
            "total_rolls": self.total_rolls,
            "comeout_rolls": self.comeout_rolls,
            "point_phase_rolls": self.point_phase_rolls,
            "points_established": self.points_established,
            "points_made": self.points_made,
            "seven_outs": self.seven_outs,
            "current_point": self.current_point,
            "last_total": self.last_total,
            "last_event": self.last_event,
            "bankroll": {
                "last_delta": self.last_bankroll_delta,
                "cum_delta": self.cum_bankroll_delta,
                # tests read these exact keys:
                "bankroll": self.cum_bankroll_delta,
                "bankroll_peak": self.bankroll_peak,
                "drawdown": drawdown,
            },
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
        point_on = bool(tbl.get("point_on"))
        comeout = bool(tbl.get("comeout"))

        if comeout:
            self.comeout_rolls += 1
        else:
            self.point_phase_rolls += 1

        # Maintain rolls_since_point
        if point_on:
            if ev_name == "point_established":
                # already reset in on_point_established; ensure consistency here too
                self.rolls_since_point = 0
            elif ev_name == "roll":
                # Only increment for rolls during point-on phase
                if self.rolls_since_point is None:
                    self.rolls_since_point = 0
                else:
                    self.rolls_since_point += 1
        else:
            # no point is on; keep it as 0 for snapshot purposes
            self.rolls_since_point = 0