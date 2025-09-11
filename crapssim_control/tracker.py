"""
tracker.py -- very lightweight roll/point/bankroll tracker used by tests.

Goal: Keep this simple and side-effect free for the engine. It just records
counts and last-seen values, plus exposes small helpers invoked by tests.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


def _dice_total(snap: Any) -> Optional[int]:
    t = None
    if isinstance(snap, dict):
        t = snap.get("table", {})
        dice = (t or {}).get("dice")
    else:
        t = getattr(snap, "table", None)
        dice = getattr(t, "dice", None) if t else None

    if dice and isinstance(dice, (tuple, list)) and len(dice) >= 3:
        # Some exporters store (d1, d2, total)
        return int(dice[2])
    return None


def _get_table(snap: Any) -> Dict[str, Any]:
    if isinstance(snap, dict):
        return snap.get("table", {})
    return getattr(snap, "table", {}) or {}


@dataclass
class Tracker:
    config: Dict[str, Any] = field(default_factory=dict)

    # Roll stats
    total_rolls: int = 0
    comeout_rolls: int = 0
    point_phase_rolls: int = 0

    # Outcome & point stats
    hits_by_total: dict = field(default_factory=lambda: defaultdict(int))
    points_established: int = 0
    points_made: int = 0
    seven_outs: int = 0

    # Last-seen values
    last_total: Optional[int] = None
    last_event: Optional[str] = None
    current_point: Optional[int] = None

    # Snapshots (for debugging/inspection)
    _prev_snapshot: Any = None
    _curr_snapshot: Any = None

    def observe(self, prev: Any, curr: Any, event: Optional[Dict[str, Any]] = None) -> None:
        self._prev_snapshot = prev
        self._curr_snapshot = curr

        ev_name = (event or {}).get("event")
        self.last_event = ev_name

        total = _dice_total(curr)
        if total is not None:
            self.last_total = total
            if 2 <= total <= 12:
                self.hits_by_total[total] += 1

        tbl = _get_table(curr)
        comeout = bool(tbl.get("comeout"))
        point_on = bool(tbl.get("point_on"))
        point_num = tbl.get("point_number")

        # Rolls accounting
        self.total_rolls += 1
        if comeout:
            self.comeout_rolls += 1
        elif point_on:
            self.point_phase_rolls += 1

        # Point transitions (based on event hints if provided)
        if ev_name == "point_established" and point_num:
            self.points_established += 1
            self.current_point = int(point_num)
        elif ev_name == "point_made":
            self.points_made += 1
            self.current_point = None
        elif ev_name == "seven_out":
            self.seven_outs += 1
            self.current_point = None

    # --------- Tiny helpers used in tests ---------

    def on_roll(self, total: int) -> None:
        """Simulate observing a roll with just a total in comeout by default."""
        dummy_prev = None
        curr = {"table": {"dice": (0, 0, total), "comeout": True, "point_on": False, "point_number": None, "roll_index": 0}}
        self.observe(dummy_prev, curr, {"event": "roll"})

    def on_point_established(self, point: int) -> None:
        """Simulate a point being established."""
        curr = {"table": {"dice": (0, 0, point), "comeout": False, "point_on": True, "point_number": point, "roll_index": 1}}
        self.observe(self._curr_snapshot, curr, {"event": "point_established"})

    def on_point_made(self, point: int) -> None:
        """Simulate the point being made."""
        curr = {"table": {"dice": (0, 0, point), "comeout": True, "point_on": False, "point_number": None, "roll_index": 2}}
        self.observe(self._curr_snapshot, curr, {"event": "point_made"})

    def on_seven_out(self) -> None:
        """Simulate a seven-out event."""
        curr = {"table": {"dice": (0, 0, 7), "comeout": True, "point_on": False, "point_number": None, "roll_index": 0}}
        self.observe(self._curr_snapshot, curr, {"event": "seven_out"})