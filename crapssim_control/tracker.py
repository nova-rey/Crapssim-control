from __future__ import annotations
from typing import Dict, Any, Optional, DefaultDict
from collections import defaultdict


class Tracker:
    """
    Lightweight, engine-agnostic bookkeeping for a craps session.

    Public signals you can feed:
      - on_roll(total)
      - on_point_established(point)
      - on_point_made()            # optional, nice-to-have
      - on_seven_out()
      - on_bankroll_delta(amount)

    Call snapshot() anytime to fetch a stable, dict-shaped view.

    Batch 1 (point-cycle extras):
      - Tracks and resets per-point-cycle metrics cleanly:
          * rolls_since_point
          * pnl_since_point
          * hits_since_point (per number)
          * inside_hits_since_point / outside_hits_since_point
      - Ensures resets happen on establish / make / seven-out.
    """

    _INSIDE = {5, 6, 8, 9}
    _OUTSIDE = {4, 10}

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = config or {}
        self.enabled: bool = bool(cfg.get("enabled", True))

        # --- Roll state
        self._last_roll: Optional[int] = None
        self._shooter_rolls: int = 0
        self._rolls_since_point: int = 0

        # --- Point state
        # Convention: None = no info yet; 0 = explicitly off / cleared.
        self._point: Optional[int] = 0

        # --- Hits (global)
        self._hits: DefaultDict[int, int] = defaultdict(int)

        # --- Hits (since point)
        self._hits_since_point: DefaultDict[int, int] = defaultdict(int)
        self._inside_hits_since_point: int = 0
        self._outside_hits_since_point: int = 0

        # --- Bankroll aggregates
        self._bankroll: float = 0.0
        self._bankroll_peak: float = 0.0
        self._drawdown: float = 0.0  # current peak-to-equity gap
        self._pnl_since_point: float = 0.0

        # --- Session aggregates
        self._points_established: int = 0
        self._points_made: int = 0
        self._seven_outs: int = 0
        self._shooter_rolls_peak: int = 0

    # --------------------------
    # Event inputs
    # --------------------------

    def on_roll(self, total: int) -> None:
        if not self.enabled:
            return

        self._last_roll = total
        self._shooter_rolls += 1
        if self._shooter_rolls > self._shooter_rolls_peak:
            self._shooter_rolls_peak = self._shooter_rolls

        # Global hit map
        self._hits[total] += 1

        # Per-point-cycle bookkeeping (only when point is ON: 4/5/6/8/9/10)
        if self._point in (4, 5, 6, 8, 9, 10):
            self._rolls_since_point += 1
            self._hits_since_point[total] += 1
            if total in self._INSIDE:
                self._inside_hits_since_point += 1
            elif total in self._OUTSIDE:
                self._outside_hits_since_point += 1

    def on_point_established(self, point: int) -> None:
        if not self.enabled:
            return

        self._point = point
        self._points_established += 1
        self._reset_since_point_counters()

    def on_point_made(self) -> None:
        """
        Optional signal: call when the shooter makes the point.
        We clear the point and reset the point-cycle counters,
        and bump the points_made aggregate.
        """
        if not self.enabled:
            return

        self._points_made += 1
        # Clear point to 0 (explicitly OFF)
        self._point = 0
        self._reset_since_point_counters()

    def on_seven_out(self) -> None:
        if not self.enabled:
            return

        self._seven_outs += 1
        # Hand ends; clear point and per-point-cycle counters.
        self._point = 0
        self._reset_since_point_counters()
        # Shooter resets roll count for next hand
        self._shooter_rolls = 0

    def on_bankroll_delta(self, amount: float) -> None:
        if not self.enabled:
            return

        self._bankroll += float(amount)
        # Peak / drawdown
        if self._bankroll > self._bankroll_peak:
            self._bankroll_peak = self._bankroll
        self._drawdown = max(0.0, self._bankroll_peak - self._bankroll)

        # Attribute PnL to current point-cycle if point is ON
        if self._point in (4, 5, 6, 8, 9, 10):
            self._pnl_since_point += float(amount)

    # --------------------------
    # Public view
    # --------------------------

    def snapshot(self) -> Dict[str, Any]:
        """
        Structurally stable view that existing tests rely on.
        Batch 1 adds a `since_point` section but keeps all prior keys.
        """
        return {
            "roll": {
                "last_roll": self._last_roll,
                "shooter_rolls": self._shooter_rolls,
                "rolls_since_point": self._rolls_since_point,
                "shooter_rolls_peak": self._shooter_rolls_peak,
            },
            "point": {
                "point": self._point,
                "points_established": self._points_established,
                "points_made": self._points_made,
            },
            "bankroll": {
                "bankroll": self._bankroll,
                "bankroll_peak": self._bankroll_peak,
                "drawdown": self._drawdown,
                "pnl_since_point": self._pnl_since_point,
            },
            "session": {
                "seven_outs": self._seven_outs,
            },
            "hits": dict(self._hits),
            # New, additive section for Batch 1
            "since_point": {
                "hits": dict(self._hits_since_point),
                "inside_hits": self._inside_hits_since_point,
                "outside_hits": self._outside_hits_since_point,
            },
        }

    # --------------------------
    # Internals
    # --------------------------

    def _reset_since_point_counters(self) -> None:
        self._rolls_since_point = 0
        self._pnl_since_point = 0.0
        self._hits_since_point.clear()
        self._inside_hits_since_point = 0
        self._outside_hits_since_point = 0