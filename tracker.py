# crapssim_control/tracker.py
from __future__ import annotations
from collections import defaultdict
from typing import Dict

_INSIDE = {5, 6, 8, 9}
_OUTSIDE = {4, 10}


class Tracker:
    def __init__(self, config: Dict):
        self._enabled = bool((config or {}).get("enabled", False))

        # point=0 means OFF
        self._point = 0

        self._roll = {
            "last_roll": None,
            "shooter_rolls": 0,
            "rolls_since_point": 0,
            "comeout_rolls": 0,
            "comeout_naturals": 0,
            "comeout_craps": 0,
        }

        self._hits = defaultdict(int)

        self._since_point = {
            "inside_hits": 0,
            "outside_hits": 0,
            "hits": defaultdict(int),
        }

        self._bankroll = {
            "bankroll": 0.0,
            "bankroll_peak": 0.0,
            "drawdown": 0.0,
            "pnl_since_point": 0.0,
        }

        # ✅ include PSO counter here
        self._session = {
            "seven_outs": 0,
            "pso": 0,
        }

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
            # ✅ expose PSO in snapshot
            "session": {
                "seven_outs": self._session["seven_outs"],
                "pso": self._session["pso"],
            },
        }

    # ---------- events ----------

    def on_roll(self, total: int) -> None:
        if not self._enabled:
            return

        if 2 <= total <= 12:
            self._hits[total] += 1

        self._roll["last_roll"] = total
        self._roll["shooter_rolls"] += 1

        if self._point:
            self._roll["rolls_since_point"] += 1
            self._since_point["hits"][total] += 1
            if total in _INSIDE:
                self._since_point["inside_hits"] += 1
            elif total in _OUTSIDE:
                self._since_point["outside_hits"] += 1
        else:
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
        if not self._enabled:
            return
        self._point = 0
        self._reset_point_cycle()

    def on_seven_out(self) -> None:
        if not self._enabled:
            return

        # Count PSO (Point-Seven-Out) before resetting: exactly one roll occurred after point turned on.
        is_pso = bool(self._point and self._roll["rolls_since_point"] == 1)

        self._session["seven_outs"] += 1
        if is_pso:
            self._session["pso"] += 1

        self._point = 0
        self._reset_point_cycle()
        self._roll["shooter_rolls"] = 0  # new shooter

    def on_bankroll_delta(self, amount: float) -> None:
        if not self._enabled:
            return

        amt = float(amount)
        self._bankroll["bankroll"] += amt

        if self._bankroll["bankroll"] > self._bankroll["bankroll_peak"]:
            self._bankroll["bankroll_peak"] = self._bankroll["bankroll"]
        self._bankroll["drawdown"] = self._bankroll["bankroll_peak"] - self._bankroll["bankroll"]

        if self._point:
            self._bankroll["pnl_since_point"] += amt

    # ---------- helpers ----------

    def _reset_point_cycle(self) -> None:
        self._roll["rolls_since_point"] = 0
        self._bankroll["pnl_since_point"] = 0.0
        self._since_point["inside_hits"] = 0
        self._since_point["outside_hits"] = 0
        self._since_point["hits"] = defaultdict(int)