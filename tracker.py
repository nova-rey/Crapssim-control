# crapssim_control/tracker.py

from __future__ import annotations

from typing import Dict
from collections import defaultdict


_INSIDE = {5, 6, 8, 9}
_OUTSIDE = {4, 10}


class Tracker:
    """
    Lightweight, test-oriented state tracker for a craps session.

    Snapshot shape used by tests:

      {
        "roll": {
          "last_roll": int|None,
          "shooter_rolls": int,
          "rolls_since_point": int,
          "comeout_rolls": int,
          "comeout_naturals": int,   # 7/11 on comeout
          "comeout_craps": int       # 2/3/12 on comeout
        },
        "point": {
          "point": int|0             # 0 when off
        },
        "hits": { number: count, ... },    # overall hit histogram (all rolls)
        "since_point": {
          "inside_hits": int,
          "outside_hits": int,
          "hits": { number: count, ... }   # histogram only for current point cycle
        },
        "bankroll": {
          "bankroll": float,         # cumulative pnl this shooter/session (simple running total)
          "bankroll_peak": float,    # max of bankroll observed so far
          "drawdown": float,         # bankroll_peak - bankroll
          "pnl_since_point": float   # pnl attributed to current point cycle
        },
        "session": {
          "seven_outs": int
        }
      }
    """

    def __init__(self, config: Dict):
        enabled = bool(config or {}).get("enabled", False)

        # Point state: 0 == off
        self._point: int = 0

        # Roll/comeout counters
        self._roll = {
            "last_roll": None,
            "shooter_rolls": 0,
            "rolls_since_point": 0,
            "comeout_rolls": 0,
            "comeout_naturals": 0,
            "comeout_craps": 0,
        }

        # Overall histogram of totals (2..12)
        self._hits = defaultdict(int)

        # Per-point-cycle aggregates
        self._since_point = {
            "inside_hits": 0,
            "outside_hits": 0,
            "hits": defaultdict(int),
        }

        # Bankroll aggregates
        self._bankroll = {
            "bankroll": 0.0,
            "bankroll_peak": 0.0,
            "drawdown": 0.0,
            "pnl_since_point": 0.0,
        }

        # Session aggregates
        self._session = {
            "seven_outs": 0,
        }

        self._enabled = enabled

    # -----------------------------
    # Public API invoked by tests
    # -----------------------------

    def snapshot(self) -> Dict:
        """Return a deep, test-friendly view of current aggregates."""
        return {
            "roll": {
                "last_roll": self._roll["last_roll"],
                "shooter_rolls": self._roll["shooter_rolls"],
                "rolls_since_point": self._roll["rolls_since_point"],
                "comeout_rolls": self._roll["comeout_rolls"],
                "comeout_naturals": self._roll["comeout_naturals"],
                "comeout_craps": self._roll["comeout_craps"],
            },
            "point": {
                "point": self._point or 0,
            },
            "hits": dict(self._hits),
            "since_point": {
                "inside_hits": self._since_point["inside_hits"],
                "outside_hits": self._since_point["outside_hits"],
                "hits": dict(self._since_point["hits"]),
            },
            "bankroll": {
                "bankroll": self._bankroll["bankroll"],
                "bankroll_peak": self._bankroll["bankroll_peak"],
                "drawdown": self._bankroll["drawdown"],
                "pnl_since_point": self._bankroll["pnl_since_point"],
            },
            "session": {
                "seven_outs": self._session["seven_outs"],
            },
        }

    # --- Roll & point lifecycle ---

    def on_roll(self, total: int) -> None:
        """Record a roll, update counters and histograms."""
        if not self._enabled:
            return

        # Overall hit histogram (include all totals we see in tests)
        if 2 <= total <= 12:
            self._hits[total] += 1

        # Shooter roll count and last seen
        self._roll["last_roll"] = total
        self._roll["shooter_rolls"] += 1

        if self._point:  # point is ON (not comeout)
            self._roll["rolls_since_point"] += 1

            # Since-point histogram & inside/outside tallies
            self._since_point["hits"][total] += 1
            if total in _INSIDE:
                self._since_point["inside_hits"] += 1
            elif total in _OUTSIDE:
                self._since_point["outside_hits"] += 1

        else:
            # Comeout roll
            self._roll["comeout_rolls"] += 1
            if total in (7, 11):
                self._roll["comeout_naturals"] += 1
            elif total in (2, 3, 12):
                self._roll["comeout_craps"] += 1

    def on_point_established(self, point: int) -> None:
        """Called when a point is set."""
        if not self._enabled:
            return

        self._point = int(point) if point else 0
        # Fresh point-cycle
        self._reset_point_cycle()

    def on_point_made(self) -> None:
        """
        Called when the shooter MAKES the point.
        This ends the current point cycle but does NOT reset shooter_rolls.
        """
        if not self._enabled:
            return

        # Point turns OFF for the next comeout
        self._point = 0
        # Reset point-cycle counters (rolls since point, pnl since point, per-cycle hits)
        self._reset_point_cycle()

    def on_seven_out(self) -> None:
        """
        Called when the shooter sevens out.
        This ends the shooter: resets shooter_rolls and increments session.seven_outs.
        """
        if not self._enabled:
            return

        self._session["seven_outs"] += 1
        # Point turns OFF
        self._point = 0
        # Reset point-cycle counters
        self._reset_point_cycle()
        # New shooter context
        self._roll["shooter_rolls"] = 0

    # --- Bankroll ---

    def on_bankroll_delta(self, amount: float) -> None:
        """Apply a bankroll delta and update peak/drawdown and pnl since point."""
        if not self._enabled:
            return

        self._bankroll["bankroll"] += float(amount)

        # Peak & drawdown
        if self._bankroll["bankroll"] > self._bankroll["bankroll_peak"]:
            self._bankroll["bankroll_peak"] = self._bankroll["bankroll"]
        self._bankroll["drawdown"] = self._bankroll["bankroll_peak"] - self._bankroll["bankroll"]

        # Attribute to current point cycle only if point is/was on this cycle.
        # Tests attribute deltas that occur between on_point_established and resolution.
        if self._point:
            self._bankroll["pnl_since_point"] += float(amount)

    # -----------------------------
    # Internals
    # -----------------------------

    def _reset_point_cycle(self) -> None:
        """Clear per-point-cycle counters."""
        self._roll["rolls_since_point"] = 0
        self._bankroll["pnl_since_point"] = 0.0
        self._since_point["inside_hits"] = 0
        self._since_point["outside_hits"] = 0
        self._since_point["hits"] = defaultdict(int)