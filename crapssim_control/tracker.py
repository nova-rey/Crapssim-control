# tracker.py

from collections import defaultdict
from typing import Dict, Optional, Tuple


INSIDE_SET = {5, 6, 8, 9}
OUTSIDE_SET = {4, 10}
POINT_SET = {4, 5, 6, 8, 9, 10}
HARDWAYS_SET = {4, 6, 8, 10}


class Tracker:
    """
    Lightweight state tracker for a craps session.

    Public event methods:
      - on_roll(total: int, dice: Optional[Tuple[int,int]] = None)
      - on_point_established(point: int)
      - on_point_made()
      - on_seven_out()
      - on_bankroll_delta(delta: float)
      - snapshot() -> Dict
    """

    def __init__(self, config: Optional[Dict] = None):
        cfg = config or {}
        self.enabled = bool(cfg.get("enabled", True))

        # Roll/hand state
        self.roll: Dict = {
            "last_roll": None,
            "shooter_rolls": 0,
            "rolls_since_point": 0,
            "comeout_rolls": 0,
            "comeout_naturals": 0,  # 7 or 11 on comeout
            "comeout_craps": 0,     # 2, 3, or 12 on comeout
        }

        # Extra split for comeout detail
        self.comeout_detail: Dict = {
            "winners_7": 0,
            "winners_11": 0,
            "craps_2": 0,
            "craps_3": 0,
            "craps_12": 0,
        }

        # Point state
        self.point: Dict = {
            "point": 0,  # 0 means OFF / on-comeout
        }

        # Hits
        self._hits = defaultdict(int)  # overall box number hits (all phases)
        self.since_point: Dict = {
            "inside_hits": 0,
            "outside_hits": 0,
            "hits": {},  # per-number during current point cycle
        }

        # Bankroll state
        self.bankroll: Dict = {
            "bankroll": 0.0,
            "bankroll_peak": 0.0,
            "drawdown": 0.0,
            "pnl_since_point": 0.0,
        }

        # Session summary
        self.session: Dict = {
            "seven_outs": 0,
            "pso": 0,    # point-seven-out counter (we treat <=1 roll after point as PSO per tests)
            "hands": 0,  # completed hands (each seven-out ends a hand)
        }

        # Batch 1 extras
        self.points_established_by_number: Dict[int, int] = {n: 0 for n in POINT_SET}
        self.points_made_by_number: Dict[int, int] = {n: 0 for n in POINT_SET}

        # Hardways hits (requires dice tuple to be passed into on_roll)
        self.hardways_hits: Dict[int, int] = {n: 0 for n in HARDWAYS_SET}

    # ----------------------
    # Event handlers
    # ----------------------

    def on_roll(self, total: int, dice: Optional[Tuple[int, int]] = None) -> None:
        if not self.enabled:
            return

        self.roll["last_roll"] = total
        self.roll["shooter_rolls"] += 1

        if self.point["point"] == 0:
            # Comeout context
            self.roll["comeout_rolls"] += 1
            if total in (7, 11):
                self.roll["comeout_naturals"] += 1
                if total == 7:
                    self.comeout_detail["winners_7"] += 1
                else:
                    self.comeout_detail["winners_11"] += 1
            elif total in (2, 3, 12):
                self.roll["comeout_craps"] += 1
                if total == 2:
                    self.comeout_detail["craps_2"] += 1
                elif total == 3:
                    self.comeout_detail["craps_3"] += 1
                else:
                    self.comeout_detail["craps_12"] += 1
        else:
            # Point is ON: count rolls since point and number hits
            self.roll["rolls_since_point"] += 1

            self._hits[total] += 1

            # Since-point detail
            sp_hits = self.since_point["hits"]
            sp_hits[total] = sp_hits.get(total, 0) + 1

            if total in INSIDE_SET:
                self.since_point["inside_hits"] += 1
            elif total in OUTSIDE_SET:
                self.since_point["outside_hits"] += 1

        # Hardways detection (only if actual dice are passed)
        if dice and len(dice) == 2 and dice[0] == dice[1]:
            s = dice[0] + dice[1]
            if s in HARDWAYS_SET and s == total:
                self.hardways_hits[s] += 1

    def on_point_established(self, point: int) -> None:
        if not self.enabled:
            return

        # Set the point and reset point-cycle counters
        self.point["point"] = point
        self.roll["rolls_since_point"] = 0
        self.bankroll["pnl_since_point"] = 0.0
        self.since_point = {
            "inside_hits": 0,
            "outside_hits": 0,
            "hits": {},
        }

        if point in self.points_established_by_number:
            self.points_established_by_number[point] += 1

    def on_point_made(self) -> None:
        if not self.enabled:
            return

        p = self.point["point"]
        if p in self.points_made_by_number:
            self.points_made_by_number[p] += 1

        # Reset point/off state
        self.point["point"] = 0
        self.roll["rolls_since_point"] = 0
        self.bankroll["pnl_since_point"] = 0.0
        self.since_point = {
            "inside_hits": 0,
            "outside_hits": 0,
            "hits": {},
        }

    def on_seven_out(self) -> None:
        if not self.enabled:
            return

        # PSO policy (per tests): seven-out with <=1 roll after point counts as PSO
        if self.roll["rolls_since_point"] <= 1:
            self.session["pso"] += 1

        self.session["seven_outs"] += 1
        self.session["hands"] += 1

        # Turn point off & reset point-cycle counters
        self.point["point"] = 0
        self.roll["rolls_since_point"] = 0
        self.since_point = {
            "inside_hits": 0,
            "outside_hits": 0,
            "hits": {},
        }

        # New shooter
        self.roll["shooter_rolls"] = 0
        # PnL stays; pnl_since_point resets because the cycle ended
        self.bankroll["pnl_since_point"] = 0.0

    def on_bankroll_delta(self, delta: float) -> None:
        if not self.enabled or delta == 0:
            if self.enabled and self.point["point"] != 0 and delta == 0:
                # If zero delta, still keep pnl_since_point unchanged
                pass
            return

        self.bankroll["bankroll"] += float(delta)

        # Peak & drawdown logic (peak updated before drawdown calc)
        if self.bankroll["bankroll"] > self.bankroll["bankroll_peak"]:
            self.bankroll["bankroll_peak"] = self.bankroll["bankroll"]
        self.bankroll["drawdown"] = max(
            0.0, self.bankroll["bankroll_peak"] - self.bankroll["bankroll"]
        )

        # Attribute PnL to current point cycle only if point is ON
        if self.point["point"] != 0:
            self.bankroll["pnl_since_point"] += float(delta)

    # ----------------------
    # Snapshot
    # ----------------------

    def snapshot(self) -> Dict:
        # Convert defaultdict to plain dict for stable output
        hits_plain = dict(self._hits)

        # Compute point-made rates safely
        point_made_rate_by_number = {}
        for n in POINT_SET:
            est = self.points_established_by_number.get(n, 0)
            made = self.points_made_by_number.get(n, 0)
            point_made_rate_by_number[n] = (made / est) if est else 0.0

        snap = {
            "roll": dict(self.roll),
            "point": dict(self.point),
            "hits": hits_plain,
            "bankroll": dict(self.bankroll),
            "session": dict(self.session),
            "since_point": {
                "inside_hits": self.since_point["inside_hits"],
                "outside_hits": self.since_point["outside_hits"],
                "hits": dict(self.since_point["hits"]),
            },
            # Batch 1 extras
            "comeout_detail": dict(self.comeout_detail),
            "points_established_by_number": dict(self.points_established_by_number),
            "points_made_by_number": dict(self.points_made_by_number),
            "point_made_rate_by_number": point_made_rate_by_number,
            "hardways_hits": dict(self.hardways_hits),
        }
        return snap