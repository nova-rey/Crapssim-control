# crapssim_control/tracker.py

from __future__ import annotations
from typing import Dict, Any, Optional


class Tracker:
    """
    Lightweight, engine-agnostic tracker for table/shooter/session metrics.

    Public callbacks you can invoke from an adapter or tests:
      - on_roll(total: int, *, is_hard: bool = False)
      - on_point_established(point: int)
      - on_bankroll_delta(delta: float)
      - on_seven_out()

    Snapshot shape returned by `snapshot()` (keys all present when enabled):

      {
        "roll": {
          "last_roll": int|None,
          "shooter_rolls": int,
          "rolls_since_point": int,
          "comeout_rolls": int,
          "comeout_naturals": int,
          "comeout_craps": int,
          "comeout_hardways": int,
        },
        "point": {
          "point": int,   # 0 means OFF
        },
        "hits": {2..12: int},
        "bankroll": {
          "bankroll": float,
          "bankroll_peak": float,
          "drawdown": float,
          "pnl_since_point": float,
        },
        "session": {
          "hands": int,        # increments on seven-out
          "seven_outs": int,
          "pso": int,          # point-seven-out count
          "comeouts": int,     # number of comeout rolls observed
        }
      }
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = config or {}
        self.enabled: bool = bool(cfg.get("enabled", True))

        # --- Roll-centric counters ---
        self._last_roll: Optional[int] = None
        self._shooter_rolls: int = 0
        self._rolls_since_point: int = 0

        # Comeout-specific tallies
        self._comeout_rolls: int = 0
        self._comeout_naturals: int = 0
        self._comeout_craps: int = 0
        self._comeout_hardways: int = 0

        # --- Point state ---
        self._point: int = 0  # 0 means OFF
        # Used for PSO detection: if we seven-out with exactly one roll since establish.
        self._made_rolls_since_point: int = 0

        # --- Per-number hits (2..12) ---
        self._hits: Dict[int, int] = {n: 0 for n in range(2, 13)}

        # --- Bankroll tracking ---
        self._bankroll: float = 0.0
        self._bankroll_peak: float = 0.0
        self._drawdown: float = 0.0
        self._pnl_since_point: float = 0.0

        # --- Session-level tallies ---
        self._hands: int = 0
        self._seven_outs: int = 0
        self._pso: int = 0
        self._comeouts: int = 0

    # ---------------------------- Public API ---------------------------- #

    def on_roll(self, total: int, *, is_hard: bool = False) -> None:
        """Record a roll outcome."""
        if not self.enabled:
            return

        self._last_roll = total
        self._shooter_rolls += 1

        # Count per-number hits safely
        if total in self._hits:
            self._hits[total] += 1

        # Comeout vs. point-on logic
        if self._point == 0:
            # We're on the comeout
            self._comeout_rolls += 1
            self._comeouts += 1

            # Naturals and craps on comeout
            if total in (7, 11):
                self._comeout_naturals += 1
            if total in (2, 3, 12):
                self._comeout_craps += 1

            # Optional hardways signal if caller knows it was hard (doubles)
            if is_hard and total in (4, 6, 8, 10):
                self._comeout_hardways += 1
        else:
            # Point is ON → track rolls since point
            self._rolls_since_point += 1
            self._made_rolls_since_point += 1

    def on_point_established(self, point: int) -> None:
        """Point turned ON to `point` (4/5/6/8/9/10)."""
        if not self.enabled:
            return

        self._point = int(point)
        self._rolls_since_point = 0
        self._made_rolls_since_point = 0
        self._pnl_since_point = 0.0  # reset PnL meter at establishment

    def on_bankroll_delta(self, delta: float) -> None:
        """Apply bankroll delta (wins/losses) and update peak/drawdown & PnL since point."""
        if not self.enabled:
            return

        self._bankroll += float(delta)
        # Peak & drawdown
        if self._bankroll > self._bankroll_peak:
            self._bankroll_peak = self._bankroll
        self._drawdown = self._bankroll_peak - self._bankroll

        # Track PnL since point establishment (even if point currently off, harmless)
        self._pnl_since_point += float(delta)

    def on_seven_out(self) -> None:
        """
        Shooter seven-outs. This:
          - increments seven_outs and hands,
          - updates PSO if exactly one roll happened since establishment,
          - turns the point OFF and resets roll counters tied to the point.
        """
        if not self.enabled:
            return

        # PSO: point established and immediately seven-out (one roll since establish).
        if self._point != 0 and self._made_rolls_since_point == 1:
            self._pso += 1

        self._seven_outs += 1
        self._hands += 1

        # Turn the point OFF and reset point-related counters
        self._point = 0
        self._rolls_since_point = 0
        self._made_rolls_since_point = 0

        # PnL since point resets at the start of the next hand
        self._pnl_since_point = 0.0

    def snapshot(self) -> Dict[str, Any]:
        """Return a stable dict snapshot of everything we track."""
        if not self.enabled:
            # Still return shape with neutral values so callers don't branch.
            return {
                "roll": {
                    "last_roll": None,
                    "shooter_rolls": 0,
                    "rolls_since_point": 0,
                    "comeout_rolls": 0,
                    "comeout_naturals": 0,
                    "comeout_craps": 0,
                    "comeout_hardways": 0,
                },
                "point": {"point": 0},
                "hits": {n: 0 for n in range(2, 13)},
                "bankroll": {
                    "bankroll": 0.0,
                    "bankroll_peak": 0.0,
                    "drawdown": 0.0,
                    "pnl_since_point": 0.0,
                },
                "session": {
                    "hands": 0,
                    "seven_outs": 0,
                    "pso": 0,
                    "comeouts": 0,
                },
            }

        return {
            "roll": {
                "last_roll": self._last_roll,
                "shooter_rolls": self._shooter_rolls,
                "rolls_since_point": self._rolls_since_point,
                "comeout_rolls": self._comeout_rolls,
                "comeout_naturals": self._comeout_naturals,
                "comeout_craps": self._comeout_craps,
                "comeout_hardways": self._comeout_hardways,
            },
            "point": {"point": self._point},
            "hits": dict(self._hits),
            "bankroll": {
                "bankroll": self._bankroll,
                "bankroll_peak": self._bankroll_peak,
                "drawdown": self._drawdown,
                "pnl_since_point": self._pnl_since_point,
            },
            "session": {
                "hands": self._hands,
                "seven_outs": self._seven_outs,
                "pso": self._pso,
                "comeouts": self._comeouts,
            },
        }