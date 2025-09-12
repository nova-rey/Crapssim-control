# crapssim_control/tracker.py
from __future__ import annotations
from collections import defaultdict
from typing import Dict

_INSIDE = {5, 6, 8, 9}
_OUTSIDE = {4, 10}


class Tracker:
    """
    Lightweight state tracker for craps session + point cycles.

    snapshot() returns:
    {
      "roll": {
        "last_roll": int|None,
        "shooter_rolls": int,
        "rolls_since_point": int,
        "comeout_rolls": int,
        "comeout_naturals": int,  # 7/11 on comeout
        "comeout_craps": int      # 2/3/12 on comeout
      },
      "point": {"point": int|0},
      "hits": { number: count, ... },      # overall
      "since_point": {
        "inside_hits": int,
        "outside_hits": int,
        "hits": { number: count, ... }     # current point cycle only
      },
      "bankroll": {
        "bankroll": float,
        "bankroll_peak": float,
        "drawdown": float,
        "pnl_since_point": float
      },
      "session": {
        "seven_outs": int
      }
    }
    """

    def __init__(self, config: Dict):
        self._enabled = bool((config or {}).get("enabled", False))

        # Point OFF -> 0, ON -> actual number
        self._point = 0

        # Roll / comeout counters
        self._roll = {
            "last_roll": None,
            "shooter_rolls": 0,
            "rolls_since_point": 0,
            "comeout_rolls": 0,
            "comeout_naturals": 0,
            "comeout_craps": 0,
        }

        # Overall per-number histogram
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
        self._session = {"seven_outs": 0}

    # ---------- Public API ----------

    def snapshot(self) -> Dict:
        return {
            "roll": {
                "last_roll": self._roll["last_roll"],
                "shooter_rolls": self._roll["shooter_rolls"],
                "rolls_since_point": self._roll["rolls_since_point"],
                "comeout_rolls": self._roll["comeout_rolls"],
                "comeout_naturals": self._roll["comeout_naturals"],
                "comeout_craps": self._roll["comeout_craps"],
            },
            "point": {"point": self._point or 0},
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
            "session": {"seven_outs": self._session["seven_outs"]},
        }

    # --- Roll & point lifecycle ---

    def on_roll(self, total: int) -> None:
        if not self._enabled:
            return

        if 2 <= total <= 12:
            self._hits[total] += 1

        self._roll["last_roll"] = total
        self._roll["shooter_rolls"] += 1

        if self._point:
            # Point is ON: track since-point counters
            self._roll["rolls_since_point"] += 1
            self._since_point["hits"][total] += 1
            if total in _INSIDE:
                self._since_point["inside_hits"] += 1
            elif total in _OUTSIDE:
                self._since_point["outside_hits"] += 1
        else:
            # Comeout
            self._roll["comeout_rolls"] += 1
            if total in (7, 11):
                self._roll["comeout_naturals"] += 1
            elif total in (2, 3, 12):
                self._roll["comeout_craps"] += 1

    def on_point_established(self, point: int) -> None:
        if not self._enabled:
            return
        self._point = int(point) if point else 0
        self._reset_point_cycle()

    def on_point_made(self) -> None:
        """
        Shooter makes the point (point is resolved, shooter continues).
        Reset per-point-cycle counters; do not reset shooter_rolls.
        """
        if not self._enabled:
            return
        self._point = 0
        self._reset_point_cycle()

    def on_seven_out(self) -> None:
        """
        Shooter sevens out.
        Reset point-cycle, set point off, increment seven_outs,
        and reset shooter_rolls for the new shooter.
        """
        if not self._enabled:
            return
        self._session["seven_outs"] += 1
        self._point = 0
        self._reset_point_cycle()
        self._roll["shooter_rolls"] = 0

    # --- Bankroll ---

    def on_bankroll_delta(self, amount: float) -> None:
        if not self._enabled:
            return

        amt = float(amount)
        self._bankroll["bankroll"] += amt

        # Peak / drawdown
        if self._bankroll["bankroll"] > self._bankroll["bankroll_peak"]:
            self._bankroll["bankroll_peak"] = self._bankroll["bankroll"]
        self._bankroll["drawdown"] = self._bankroll["bankroll_peak"] - self._bankroll["bankroll"]

        # Attribute PnL to current point cycle only when point is/was on
        if self._point:
            self._bankroll["pnl_since_point"] += amt

    # ---------- Internals ----------

    def _reset_point_cycle(self) -> None:
        self._roll["rolls_since_point"] = 0
        self._bankroll["pnl_since_point"] = 0.0
        self._since_point["inside_hits"] = 0
        self._since_point["outside_hits"] = 0
        self._since_point["hits"] = defaultdict(int)