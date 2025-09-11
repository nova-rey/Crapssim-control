"""
tracker.py -- simple, test-friendly tracking of roll & point stats.

Exposed API used by tests:
- Tracker(config).on_roll(total) → simulates receiving a roll result
- Tracker.observe(prev, curr, event) → consumes snapshots like engine/controller
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from collections import defaultdict


def _dice_total(snapshot: Any) -> Optional[int]:
    """
    Extract total from a snapshot shaped like:
      {"table": {"dice": (d1, d2, total), ...}}
    or return None if not present.
    """
    table = None
    if isinstance(snapshot, dict):
        table = snapshot.get("table")
    else:
        table = getattr(snapshot, "table", None)

    dice = None
    if isinstance(table, dict):
        dice = table.get("dice")
    else:
        dice = getattr(table, "dice", None)

    if isinstance(dice, (tuple, list)) and len(dice) >= 3:
        return int(dice[2])
    return None


@dataclass
class Tracker:
    config: Dict[str, Any] = field(default_factory=dict)

    total_rolls: int = 0
    comeout_rolls: int = 0
    point_phase_rolls: int = 0
    hits_by_total: Dict[int, int] = field(default_factory=lambda: defaultdict(int))

    points_established: int = 0
    points_made: int = 0
    seven_outs: int = 0

    _prev_snapshot: Any = None
    _curr_snapshot: Any = None
    last_event: Optional[str] = None
    last_total: Optional[int] = None
    last_point: Optional[int] = None
    point_on: bool = False

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        # Keep config separate from counters
        object.__setattr__(self, "config", dict(config or {}))

        # Initialize counters explicitly as ints / dicts
        object.__setattr__(self, "total_rolls", 0)
        object.__setattr__(self, "comeout_rolls", 0)
        object.__setattr__(self, "point_phase_rolls", 0)
        object.__setattr__(self, "hits_by_total", defaultdict(int))
        object.__setattr__(self, "points_established", 0)
        object.__setattr__(self, "points_made", 0)
        object.__setattr__(self, "seven_outs", 0)

        # Rolling state
        object.__setattr__(self, "_prev_snapshot", None)
        object.__setattr__(self, "_curr_snapshot", None)
        object.__setattr__(self, "last_event", None)
        object.__setattr__(self, "last_total", None)
        object.__setattr__(self, "last_point", None)
        object.__setattr__(self, "point_on", False)

    # ---------- Public helpers used by tests ----------

    def on_roll(self, total: int) -> None:
        """
        Convenience used by tests: emulate a single roll without a full engine.
        We synthesize minimal snapshots and call observe().
        """
        # prev snapshot is whatever we observed last
        dummy_prev = self._curr_snapshot

        # curr snapshot: replicate the small table dict the engine uses
        curr = {
            "table": {
                "dice": (0, 0, int(total)),
                "comeout": not self.point_on,
                "point_on": self.point_on,
                "point_number": self.last_point if self.point_on else None,
                "roll_index": 0,  # not essential for tests
            }
        }

        # If we're on comeout and roll establishes a point, mark it
        if curr["table"]["comeout"] and total in (4, 5, 6, 8, 9, 10):
            curr["table"]["point_on"] = True
            curr["table"]["point_number"] = total

        # If we're in point phase and hit the point, next state is comeout
        if self.point_on and self.last_point and total == self.last_point:
            # hitting the point ends the point; next roll will be comeout
            pass

        # Feed as a plain "roll" event (the tests call us like this)
        self.observe(dummy_prev, curr, {"event": "roll"})

        # After observing a hit of the point, switch back to comeout for next time
        if self.point_on and self.last_point and total == self.last_point:
            self.point_on = False
            self.last_point = None

    def observe(self, prev: Any, curr: Any, event: Optional[Dict[str, Any]] = None) -> None:
        """
        Main tracking entry: record what's needed from a before/after roll snapshot.
        """
        self._prev_snapshot = prev
        self._curr_snapshot = curr

        ev_name = (event or {}).get("event")
        self.last_event = ev_name

        total = _dice_total(curr)
        if total is not None:
            self.last_total = total
            if 2 <= total <= 12:
                self.hits_by_total[total] += 1

        # Update total roll counters
        self.total_rolls += 1

        # Extract phase flags from snapshot
        table = curr.get("table", {}) if isinstance(curr, dict) else getattr(curr, "table", {})  # type: ignore
        comeout = table.get("comeout", False)
        point_on = table.get("point_on", False)
        point_number = table.get("point_number")

        # Count phase rolls
        if comeout:
            self.comeout_rolls += 1
        elif point_on:
            self.point_phase_rolls += 1

        # Track point lifecycle
        if comeout and point_on and point_number:
            # edge case: synthetic snapshot sets both (establishing point)
            self.points_established += 1
            self.point_on = True
            self.last_point = int(point_number)
        elif comeout and total in (4, 5, 6, 8, 9, 10):
            # establish
            self.points_established += 1
            self.point_on = True
            self.last_point = int(total)
        elif point_on and self.last_point and total == self.last_point:
            # point made
            self.points_made += 1
        elif total == 7 and point_on:
            # seven-out during point
            self.seven_outs += 1
            self.point_on = False
            self.last_point = None