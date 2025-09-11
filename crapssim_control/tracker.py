# crapssim_control/tracker.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple, Mapping, MutableMapping
from collections import defaultdict


__all__ = ["Tracker"]


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """
    Safe getter that works with plain dict snapshots *or* objects from snapshotter.
    Supports one-level nested keys like "table.point_on" or "table.dice".
    """
    if obj is None:
        return default
    if "." in key:
        head, tail = key.split(".", 1)
        return _get(_get(obj, head), tail, default)

    # dict-like
    if isinstance(obj, Mapping):
        return obj.get(key, default)

    # object-like
    if hasattr(obj, key):
        return getattr(obj, key)

    # table view on GameState
    if hasattr(obj, "table") and key in ("point_on", "point_number", "comeout", "dice", "roll_index"):
        tbl = getattr(obj, "table")
        if tbl is not None and hasattr(tbl, key):
            return getattr(tbl, key)

    return default


def _dice_total(snapshot: Any) -> Optional[int]:
    dice = _get(snapshot, "table.dice")
    if not dice or not isinstance(dice, (tuple, list)) or len(dice) < 3:
        return _get(snapshot, "total") or _get(snapshot, "table.total")
    # Many of our tests use (d1, d2, total)
    try:
        return int(dice[2])
    except Exception:
        return None


def _is_comeout(snapshot: Any) -> bool:
    v = _get(snapshot, "table.comeout", _get(snapshot, "comeout", False))
    return bool(v)


def _point_on(snapshot: Any) -> bool:
    return bool(_get(snapshot, "table.point_on", _get(snapshot, "point_on", False)))


def _point_num(snapshot: Any) -> Optional[int]:
    pn = _get(snapshot, "table.point_number", _get(snapshot, "point_number"))
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
    """
    Lightweight, side-effect-free table/shooter tracker.

    Option A metrics:
      - Per-number hit counts (2..12)
      - Come-out vs. point-phase roll counts
      - Point lifecycle per number: established/made + make-rate
      - Shooter stats: current rolls, longest hand, hands played
      - Streaks: current & max point-phase (non-seven) run

    Usage:
        tr = Tracker()
        tr.observe(prev_snapshot, curr_snapshot, event_dict)
        stats = tr.snapshot()  # dict for logging/telemetry
    """

    # --- roll counters ---
    total_rolls: int = 0
    comeout_rolls: int = 0
    point_phase_rolls: int = 0
    hits_by_total: Dict[int, int] = field(default_factory=lambda: defaultdict(int))

    # --- point lifecycle ---
    point_stats: Dict[int, _PointStats] = field(default_factory=lambda: defaultdict(_PointStats))
    current_point: Optional[int] = None

    # --- shooter stats ---
    current_shooter_rolls: int = 0
    longest_shooter_hand: int = 0
    hands_played: int = 0

    # --- streaks (point-phase without seven) ---
    current_point_run: int = 0
    max_point_run: int = 0

    # --- lasts ---
    last_event: Optional[str] = None
    last_total: Optional[int] = None

    # --- bankroll deltas (optional feeding via external call if you want later) ---
    last_bankroll: Optional[float] = None
    last_bankroll_delta: Optional[float] = None

    # keep last snapshots if a client wants to export richer detail later
    _prev_snapshot: Any = None
    _curr_snapshot: Any = None

    def reset_session(self) -> None:
        self.total_rolls = 0
        self.comeout_rolls = 0
        self.point_phase_rolls = 0
        self.hits_by_total.clear()
        self.point_stats.clear()
        self.current_point = None
        self.current_shooter_rolls = 0
        self.longest_shooter_hand = 0
        self.hands_played = 0
        self.current_point_run = 0
        self.max_point_run = 0
        self.last_event = None
        self.last_total = None
        self.last_bankroll = None
        self.last_bankroll_delta = None
        self._prev_snapshot = None
        self._curr_snapshot = None

    def reset_shooter(self) -> None:
        # finalize previous shooter length
        self.longest_shooter_hand = max(self.longest_shooter_hand, self.current_shooter_rolls)
        self.hands_played += 1
        self.current_shooter_rolls = 0

    # Optional hook if you want to feed bankroll after each roll
    def record_bankroll(self, bankroll: Optional[float]) -> None:
        if bankroll is None:
            return
        if self.last_bankroll is not None:
            self.last_bankroll_delta = bankroll - self.last_bankroll
        self.last_bankroll = bankroll

    def observe(self, prev: Any, curr: Any, event: Optional[Dict[str, Any]] = None) -> None:
        """
        Update counters given previous/current snapshots and a derived event.
        `event` should look like {"event": "<name>", ...} as produced by events.derive_event.
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

        # Shooter roll counts
        self.total_rolls += 1
        self.current_shooter_rolls += 1

        # Phase split
        if _is_comeout(curr):
            self.comeout_rolls += 1
            # Come-out rolls do not increment point-phase run
            self.current_point_run = 0
        else:
            self.point_phase_rolls += 1

        # Point lifecycle & streaks
        if ev_name == "point_established":
            p = _point_num(curr)
            self.current_point = p
            if p in (4, 5, 6, 8, 9, 10):  # track only box numbers for lifecycle
                self.point_stats[p].established += 1
            # starting new point → reset run
            self.current_point_run = 0

        elif ev_name == "point_made":
            p = _point_num(prev) or self.current_point
            if p in (4, 5, 6, 8, 9, 10):
                self.point_stats[p].made += 1
            # making the point ends the run; comeout follows
            self.current_point = None
            self.current_point_run = 0

        elif ev_name == "seven_out":
            # seven-out ends the current point run and clears point
            self.max_point_run = max(self.max_point_run, self.current_point_run)
            self.current_point_run = 0
            self.current_point = None

        else:
            # Regular roll inside point-phase (and not a seven-out)
            if _point_on(curr) and (total != 7):
                self.current_point_run += 1
                self.max_point_run = max(self.max_point_run, self.current_point_run)

        # Shooter change
        if ev_name == "shooter_change":
            self.reset_shooter()

    # --- Read APIs ---

    @property
    def box_numbers(self) -> Dict[int, int]:
        """Convenience view for 4,5,6,8,9,10 hit counts."""
        return {n: int(self.hits_by_total.get(n, 0)) for n in (4, 5, 6, 8, 9, 10)}

    @property
    def comeout_pct(self) -> float:
        return (self.comeout_rolls / self.total_rolls) if self.total_rolls else 0.0

    @property
    def point_phase_pct(self) -> float:
        return (self.point_phase_rolls / self.total_rolls) if self.total_rolls else 0.0

    def point_make_rate(self, number: int) -> float:
        ps = self.point_stats.get(number)
        if not ps or ps.established == 0:
            return 0.0
        return ps.made / ps.established

    def snapshot(self) -> Dict[str, Any]:
        """
        Flat dict suitable for logging/telemetry dumps.
        """
        out: Dict[str, Any] = {
            "total_rolls": self.total_rolls,
            "comeout_rolls": self.comeout_rolls,
            "point_phase_rolls": self.point_phase_rolls,
            "comeout_pct": round(self.comeout_pct, 4),
            "point_phase_pct": round(self.point_phase_pct, 4),
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
        # per-total hits
        for n in range(2, 13):
            out[f"hits_{n}"] = int(self.hits_by_total.get(n, 0))
        # box numbers convenience
        for n in (4, 5, 6, 8, 9, 10):
            ps = self.point_stats.get(n)
            out[f"point_{n}_established"] = ps.established if ps else 0
            out[f"point_{n}_made"] = ps.made if ps else 0
            out[f"point_{n}_make_rate"] = round(self.point_make_rate(n), 4)
        return out