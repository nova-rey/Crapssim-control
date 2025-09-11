# crapssim_control/tracker.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple, Mapping, List
from collections import defaultdict

__all__ = ["Tracker"]


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if "." in key:
        head, tail = key.split(".", 1)
        return _get(_get(obj, head), tail, default)
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    if hasattr(obj, key):
        return getattr(obj, key)
    if hasattr(obj, "table") and key in ("point_on", "point_number", "comeout", "dice", "roll_index"):
        tbl = getattr(obj, "table")
        if tbl is not None and hasattr(tbl, key):
            return getattr(tbl, key)
    return default


def _dice_total(snapshot: Any) -> Optional[int]:
    dice = _get(snapshot, "table.dice")
    if isinstance(dice, (tuple, list)) and len(dice) >= 3:
        try:
            return int(dice[2])
        except Exception:
            pass
    return _get(snapshot, "total") or _get(snapshot, "table.total")


def _is_comeout(s: Any) -> bool:
    return bool(_get(s, "table.comeout", _get(s, "comeout", False)))


def _point_on(s: Any) -> bool:
    return bool(_get(s, "table.point_on", _get(s, "point_on", False)))


def _point_num(s: Any) -> Optional[int]:
    pn = _get(s, "table.point_number", _get(s, "point_number"))
    try:
        return int(pn) if pn is not None else None
    except Exception:
        return None


@dataclass
class _PointStats:
    established: int = 0
    made: int = 0


@dataclass
class Tracker:
    """Option-A tracker (backward-compatible)."""

    # roll counters
    total_rolls: int = 0
    comeout_rolls: int = 0
    point_phase_rolls: int = 0
    hits_by_total: Dict[int, int] = field(default_factory=lambda: defaultdict(int))

    # point lifecycle
    point_stats: Dict[int, _PointStats] = field(default_factory=lambda: defaultdict(_PointStats))
    current_point: Optional[int] = None

    # shooter stats
    current_shooter_rolls: int = 0
    longest_shooter_hand: int = 0
    hands_played: int = 0

    # streaks
    current_point_run: int = 0
    max_point_run: int = 0

    # last
    last_event: Optional[str] = None
    last_total: Optional[int] = None
    last_bankroll: Optional[float] = None
    last_bankroll_delta: Optional[float] = None

    _prev_snapshot: Any = None
    _curr_snapshot: Any = None

    # ---------------- core API ----------------

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

        self.total_rolls += 1
        self.current_shooter_rolls += 1

        if _is_comeout(curr):
            self.comeout_rolls += 1
            self.current_point_run = 0
        else:
            self.point_phase_rolls += 1

        if ev_name == "point_established":
            p = _point_num(curr)
            self.current_point = p
            if p in (4, 5, 6, 8, 9, 10):
                self.point_stats[p].established += 1
            self.current_point_run = 0

        elif ev_name == "point_made":
            p = _point_num(prev) or self.current_point
            if p in (4, 5, 6, 8, 9, 10):
                self.point_stats[p].made += 1
            self.current_point = None
            self.current_point_run = 0

        elif ev_name == "seven_out":
            self.max_point_run = max(self.max_point_run, self.current_point_run)
            self.current_point_run = 0
            self.current_point = None

        else:
            if _point_on(curr) and (total != 7):
                self.current_point_run += 1
                self.max_point_run = max(self.max_point_run, self.current_point_run)

        if ev_name == "shooter_change":
            self._reset_shooter()

    def record_bankroll(self, bankroll: Optional[float]) -> None:
        if bankroll is None:
            return
        if self.last_bankroll is not None:
            self.last_bankroll_delta = bankroll - self.last_bankroll
        self.last_bankroll = bankroll

    def snapshot(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "total_rolls": self.total_rolls,
            "comeout_rolls": self.comeout_rolls,
            "point_phase_rolls": self.point_phase_rolls,
            "comeout_pct": round(self.comeout_rolls / self.total_rolls, 4) if self.total_rolls else 0.0,
            "point_phase_pct": round(self.point_phase_rolls / self.total_rolls, 4) if self.total_rolls else 0.0,
            "current_point": self.current_point,
            "current_point_run": self.current_point_run,
            "max_point_run": self.max_point_run,
            "current_shooter_rolls": self.current_shooter_rolls,
            "longest_shooter_hand": self.longest_shooter_hand,
            "hands_played": self.hands_played,
            "last_event": self.last_event,
            "last_total": self.last_total,
            "last_bankroll": self.last_bankroll,
            "last_bankroll_delta": self.last_bankroll_delta,
        }
        for n in range(2, 13):
            out[f"hits_{n}"] = int(self.hits_by_total.get(n, 0))
        for n in (4, 5, 6, 8, 9, 10):
            ps = self.point_stats.get(n)
            est = ps.established if ps else 0
            made = ps.made if ps else 0
            rate = (made / est) if est else 0.0
            out[f"point_{n}_established"] = est
            out[f"point_{n}_made"] = made
            out[f"point_{n}_make_rate"] = round(rate, 4)
        return out

    # ---------------- legacy shim (for tests expecting old API) ----------------

    def on_roll(self, total: int) -> None:
        """Legacy: treat as a generic roll during point-phase if a point is on, else comeout roll."""
        dummy_prev = self._curr_snapshot
        # synthesize a minimal curr snapshot dict
        curr = {
            "table": {
                "dice": (0, 0, int(total)),
                "comeout": not bool(self.current_point),
                "point_on": bool(self.current_point),
                "point_number": self.current_point,
                "roll_index": 0,
            }
        }
        self.observe(dummy_prev, curr, {"event": "roll"})

    def on_point_established(self, number: int) -> None:
        prev = self._curr_snapshot
        curr = {"table": {"comeout": False, "point_on": True, "point_number": int(number), "dice": (0, 0, int(number))}}
        self.observe(prev, curr, {"event": "point_established"})

    def on_point_made(self, number: int) -> None:
        prev = self._curr_snapshot
        curr = {"table": {"comeout": True, "point_on": False, "point_number": None, "dice": (0, 0, int(number))}}
        self.observe(prev, curr, {"event": "point_made"})

    def on_seven_out(self) -> None:
        prev = self._curr_snapshot
        curr = {"table": {"comeout": True, "point_on": False, "point_number": None, "dice": (0, 0, 7)}}
        self.observe(prev, curr, {"event": "seven_out"})

    def on_shooter_change(self) -> None:
        self._reset_shooter()

    # ---------------- internals ----------------

    def _reset_shooter(self) -> None:
        self.longest_shooter_hand = max(self.longest_shooter_hand, self.current_shooter_rolls)
        self.hands_played += 1
        self.current_shooter_rolls = 0