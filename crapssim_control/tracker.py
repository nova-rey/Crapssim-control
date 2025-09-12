# crapssim_control/tracker.py

from __future__ import annotations
from typing import Dict, Any, Optional


class Tracker:
    """
    Lightweight, engine-agnostic state tracker used by tests and (optionally)
    by higher-level adapters. It records:
      - Last roll, rolls since point, shooter roll count, comeout roll count
      - Point life-cycle (established / seven-out)
      - Per-number hit counts (2..12)
      - Bankroll deltas, peak, drawdown, PnL since current point
      - Session-level seven-out count
      - Inside/outside hit counts since point (inside: 5,6,8,9; outside: 4,10)
      - Per-number hits since point (since_point.hits)

    All methods are safe no-ops when disabled via config {"enabled": False}.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = config or {}
        self._enabled: bool = bool(cfg.get("enabled", True))

        # Roll-related
        self._last_roll: Optional[int] = None
        self._shooter_rolls: int = 0
        self._rolls_since_point: int = 0
        self._comeout_rolls: int = 0  # rolls taken while no point is on

        # Point-related
        self._point: Optional[int] = None  # None before first point; 0 after seven-out reset

        # Hit counters
        self._hits: Dict[int, int] = {n: 0 for n in range(2, 13)}
        self._inside_hits_since_point: int = 0  # 5,6,8,9 while point is on
        self._outside_hits_since_point: int = 0  # 4,10 while point is on
        self._hits_since_point: Dict[int, int] = {}  # per-number hits while point is on

        # Bankroll-related
        self._bankroll: float = 0.0
        self._bankroll_peak: float = 0.0
        self._drawdown: float = 0.0
        self._pnl_since_point: float = 0.0

        # Session-related
        self._session_seven_outs: int = 0

    # ---------------------------
    # Event methods
    # ---------------------------

    def on_roll(self, total: int) -> None:
        """Record a roll outcome (2..12)."""
        if not self._enabled:
            return
        if total < 2 or total > 12:
            # Ignore impossible totals defensively
            return

        self._last_roll = total
        self._shooter_rolls += 1
        self._hits[total] = self._hits.get(total, 0) + 1

        # If no point is on (None or 0), this is a comeout roll.
        if not self._point:
            self._comeout_rolls += 1
            return  # no since-point accounting while point is off

        # If a point is currently ON (positive integer),
        # count rolls since point and classify inside/outside hits.
        if total != 7:
            self._rolls_since_point += 1
            # per-number hits since point
            self._hits_since_point[total] = self._hits_since_point.get(total, 0) + 1

            if total in (5, 6, 8, 9):
                self._inside_hits_since_point += 1
            elif total in (4, 10):
                self._outside_hits_since_point += 1

    def on_point_established(self, point: int) -> None:
        """Called when a point is established (e.g., 4/5/6/8/9/10)."""
        if not self._enabled:
            return
        self._point = int(point)
        self._rolls_since_point = 0
        # Reset per-point aggregates
        self._pnl_since_point = 0.0
        self._inside_hits_since_point = 0
        self._outside_hits_since_point = 0
        self._hits_since_point = {}

    def on_bankroll_delta(self, delta: float) -> None:
        """Apply a bankroll delta and update peak/drawdown and PnL since point."""
        if not self._enabled:
            return
        self._bankroll += float(delta)
        if self._bankroll > self._bankroll_peak:
            self._bankroll_peak = self._bankroll
        # Drawdown from the peak (non-negative)
        self._drawdown = self._bankroll_peak - self._bankroll
        # Attribute PnL to the current point cycle if a point is ON
        if self._point:
            self._pnl_since_point += float(delta)

    def on_seven_out(self) -> None:
        """Called when a seven-out occurs (point is lost, new shooter)."""
        if not self._enabled:
            return
        self._session_seven_outs += 1
        # Clear point context; tests expect 0 here (not None) after seven-out.
        self._point = 0
        self._rolls_since_point = 0
        # New shooter resets shooter roll count
        self._shooter_rolls = 0
        # Reset per-point aggregates
        self._pnl_since_point = 0.0
        self._inside_hits_since_point = 0
        self._outside_hits_since_point = 0
        self._hits_since_point = {}

    # ---------------------------
    # Snapshot
    # ---------------------------

    def snapshot(self) -> Dict[str, Any]:
        """
        Return a structured snapshot consumed by tests:

        {
          "roll": {
            "last_roll": int|None,
            "shooter_rolls": int,
            "rolls_since_point": int,
            "comeout_rolls": int
          },
          "point": {
            "point": int|None|0
          },
          "hits": { 2..12: int },
          "bankroll": {
            "bankroll": float,
            "bankroll_peak": float,
            "drawdown": float,
            "pnl_since_point": float
          },
          "session": {
            "seven_outs": int
          },
          "since_point": {
            "inside_hits": int,
            "outside_hits": int,
            "hits": { int: int }
          }
        }
        """
        if not self._enabled:
            # Provide a consistent shape with zeros when disabled.
            return {
                "roll": {
                    "last_roll": None,
                    "shooter_rolls": 0,
                    "rolls_since_point": 0,
                    "comeout_rolls": 0,
                },
                "point": {
                    "point": None,
                },
                "hits": {n: 0 for n in range(2, 13)},
                "bankroll": {
                    "bankroll": 0.0,
                    "bankroll_peak": 0.0,
                    "drawdown": 0.0,
                    "pnl_since_point": 0.0,
                },
                "session": {
                    "seven_outs": 0,
                },
                "since_point": {
                    "inside_hits": 0,
                    "outside_hits": 0,
                    "hits": {},
                },
            }

        return {
            "roll": {
                "last_roll": self._last_roll,
                "shooter_rolls": self._shooter_rolls,
                "rolls_since_point": self._rolls_since_point,
                "comeout_rolls": self._comeout_rolls,
            },
            "point": {
                "point": self._point,
            },
            "hits": dict(self._hits),
            "bankroll": {
                "bankroll": self._bankroll,
                "bankroll_peak": self._bankroll_peak,
                "drawdown": self._drawdown,
                "pnl_since_point": self._pnl_since_point,
            },
            "session": {
                "seven_outs": self._session_seven_outs,
            },
            "since_point": {
                "inside_hits": self._inside_hits_since_point,
                "outside_hits": self._outside_hits_since_point,
                "hits": dict(self._hits_since_point),
            },
        }