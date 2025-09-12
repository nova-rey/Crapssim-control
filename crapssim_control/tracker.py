# tracker.py

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple
import time


INSIDE_NUMS = {5, 6, 8, 9}
OUTSIDE_NUMS = {4, 10}
CRAPS = {2, 3, 12}
NATURALS = {7, 11}


def _now_ts() -> float:
    return time.time()


@dataclass
class TrackerConfig:
    enabled: bool = True
    timeline_size: int = 200  # ring buffer of most recent events


@dataclass
class Tracker:
    config: Dict

    # --- runtime state containers ---
    roll: Dict = field(default_factory=dict)
    point: Dict = field(default_factory=dict)
    hits: Dict[int, int] = field(default_factory=lambda: defaultdict(int))
    bankroll: Dict = field(default_factory=dict)
    session: Dict = field(default_factory=dict)
    since_point: Dict = field(default_factory=dict)
    streaks: Dict = field(default_factory=dict)
    shooter: Dict = field(default_factory=dict)

    _timeline: Deque = field(default_factory=deque)

    def __post_init__(self):
        cfg = TrackerConfig(**self.config) if isinstance(self.config, dict) else self.config

        # Rolls & comeout
        self.roll = {
            "last_roll": None,
            "shooter_rolls": 0,         # rolls in current shooter's hand
            "rolls_since_point": 0,     # rolls since last point was set
            "comeout_rolls": 0,         # count of comeout tosses this session
            "comeout_naturals": 0,      # 7/11 on comeout
            "comeout_craps": 0,         # 2/3/12 on comeout
        }

        # Puck / point
        self.point = {
            "point": 0,     # 0 = off; otherwise 4/5/6/8/9/10
        }

        # Global hits tally (by box number)
        self.hits = defaultdict(int)

        # Bankroll
        self.bankroll = {
            "bankroll": 0.0,
            "bankroll_peak": 0.0,
            "drawdown": 0.0,            # peak - current
            "pnl_since_point": 0.0,     # resets on point establish/made/7-out
        }

        # Session tallies
        self.session = {
            "seven_outs": 0,
            "pso": 0,       # point-seven-out hands
            "hands": 0,     # completed shooter hands
        }

        # Per-point-cycle counters
        self.since_point = {
            "inside_hits": 0,
            "outside_hits": 0,
            "hits": {},     # per-number during current point cycle
        }

        # Streak tracking
        self.streaks = {
            "inside_current": 0,
            "inside_max": 0,
            "outside_current": 0,
            "outside_max": 0,
            "hardway_current": 0,
            "hardway_max": 0,
        }

        # Shooter-level stats
        self.shooter = {
            "hand_lengths": [],     # list of ints (rolls per completed hand)
            "longest_hand": 0,      # max rolls observed in a hand
            "avg_rolls_per_hand": 0.0,
            "hand_hist": {},        # length -> count
        }

        # Timeline ring buffer
        self._timeline = deque(maxlen=cfg.timeline_size)

        self._enabled = cfg.enabled

    # ----------- helpers -----------

    def _in_comeout(self) -> bool:
        return self.point.get("point", 0) in (0, None)

    def _is_inside(self, total: int) -> bool:
        return total in INSIDE_NUMS

    def _is_outside(self, total: int) -> bool:
        return total in OUTSIDE_NUMS

    def _update_streaks(self, total: int, is_hard: bool):
        # Inside/outside streaks
        if self._is_inside(total):
            self.streaks["inside_current"] += 1
            self.streaks["inside_max"] = max(self.streaks["inside_max"], self.streaks["inside_current"])
            # reset opposite
            self.streaks["outside_current"] = 0
        elif self._is_outside(total):
            self.streaks["outside_current"] += 1
            self.streaks["outside_max"] = max(self.streaks["outside_max"], self.streaks["outside_current"])
            # reset opposite
            self.streaks["inside_current"] = 0
        else:
            # neither inside nor outside (e.g., 2,3,7,11,12)
            self.streaks["inside_current"] = 0
            self.streaks["outside_current"] = 0

        # Hardway streak
        if is_hard:
            self.streaks["hardway_current"] += 1
            self.streaks["hardway_max"] = max(self.streaks["hardway_max"], self.streaks["hardway_current"])
        else:
            self.streaks["hardway_current"] = 0

    def _append_timeline(self, event: str, payload: Dict):
        self._timeline.append({
            "ts": _now_ts(),
            "event": event,
            **payload,
        })

    def _finalize_hand(self):
        """Called only on seven-out: marks end of hand and updates shooter stats."""
        length = self.roll["shooter_rolls"]
        # Update shooter stats
        self.shooter["hand_lengths"].append(length)
        if length > self.shooter["longest_hand"]:
            self.shooter["longest_hand"] = length

        # Histogram
        hist = defaultdict(int, self.shooter.get("hand_hist", {}))
        hist[length] += 1
        self.shooter["hand_hist"] = dict(hist)

        # Average
        n = len(self.shooter["hand_lengths"])
        self.shooter["avg_rolls_per_hand"] = (
            sum(self.shooter["hand_lengths"]) / n if n else 0.0
        )

        # Session hand complete
        self.session["hands"] += 1

        # Reset hand roll counter for the next shooter
        self.roll["shooter_rolls"] = 0

    # ----------- public API -----------

    def on_roll(self, total: int, *, is_hard: bool = False):
        """Record any roll (comeout or point-on). `is_hard` is optional and
        only impacts hardway streaks (does not affect any existing tests)."""
        if not self._enabled:
            return

        self.roll["last_roll"] = total
        self.roll["shooter_rolls"] += 1

        # Global hits
        if total > 0:
            self.hits[total] += 1

        # Comeout accounting
        if self._in_comeout():
            self.roll["comeout_rolls"] += 1
            if total in NATURALS:
                self.roll["comeout_naturals"] += 1
            elif total in CRAPS:
                self.roll["comeout_craps"] += 1
        else:
            # Point is on → per-point-cycle counters
            self.roll["rolls_since_point"] += 1
            if self._is_inside(total):
                self.since_point["inside_hits"] += 1
            elif self._is_outside(total):
                self.since_point["outside_hits"] += 1

            sp_hits = self.since_point.get("hits") or {}
            sp_hits[total] = sp_hits.get(total, 0) + 1
            self.since_point["hits"] = sp_hits

        # Streaks (works across both comeout and point-on)
        self._update_streaks(total, is_hard=is_hard)

        # Timeline
        self._append_timeline("roll", {
            "total": total,
            "is_hard": is_hard,
            "point": self.point["point"],
            "comeout": self._in_comeout(),
        })

    def on_point_established(self, point: int):
        if not self._enabled:
            return
        self.point["point"] = point
        # Reset since-point counters
        self.roll["rolls_since_point"] = 0
        self.bankroll["pnl_since_point"] = 0.0
        self.since_point["inside_hits"] = 0
        self.since_point["outside_hits"] = 0
        self.since_point["hits"] = {}
        # Timeline
        self._append_timeline("point_established", {"point": point})

    def on_point_made(self):
        """Point hit but shooter CONTINUES (no hand reset)."""
        if not self._enabled:
            return
        # Reset point-cycle counters but keep shooter hand alive
        self.point["point"] = 0
        self.roll["rolls_since_point"] = 0
        self.bankroll["pnl_since_point"] = 0.0
        self.since_point["inside_hits"] = 0
        self.since_point["outside_hits"] = 0
        self.since_point["hits"] = {}
        # Timeline
        self._append_timeline("point_made", {})

    def on_seven_out(self):
        """Seven-out ends the shooter’s hand."""
        if not self._enabled:
            return

        # PSO means seven-out on the very next roll after point established.
        # (Per your tests, PSO is counted when rolls_since_point == 1)
        if self.roll["rolls_since_point"] == 1:
            self.session["pso"] += 1

        self.session["seven_outs"] += 1

        # End of hand → update shooter stats & reset shooter context
        self._finalize_hand()

        # Turn puck off & clear per-point-cycle counters
        self.point["point"] = 0
        self.roll["rolls_since_point"] = 0
        self.bankroll["pnl_since_point"] = 0.0
        self.since_point["inside_hits"] = 0
        self.since_point["outside_hits"] = 0
        self.since_point["hits"] = {}

        # Also reset inside/outside/hardway current streaks; keep maxes
        self.streaks["inside_current"] = 0
        self.streaks["outside_current"] = 0
        self.streaks["hardway_current"] = 0

        # Timeline
        self._append_timeline("seven_out", {})

    def on_bankroll_delta(self, amount: float):
        if not self._enabled:
            return
        self.bankroll["bankroll"] += amount
        self.bankroll["bankroll_peak"] = max(self.bankroll["bankroll_peak"], self.bankroll["bankroll"])
        self.bankroll["drawdown"] = self.bankroll["bankroll_peak"] - self.bankroll["bankroll"]
        # Attribute to current point cycle (even if comeout, it will just be 0 when point is off)
        self.bankroll["pnl_since_point"] += amount
        # Timeline
        self._append_timeline("bankroll_delta", {"delta": amount, "bankroll": self.bankroll["bankroll"]})

    # ----------- readout -----------

    def snapshot(self) -> Dict:
        """Return a read-only snapshot for tests/consumers."""
        # Compute shooter averages are already maintained incrementally.
        return {
            "roll": dict(self.roll),
            "point": dict(self.point),
            "hits": dict(self.hits),
            "bankroll": dict(self.bankroll),
            "session": dict(self.session),
            "since_point": {
                "inside_hits": self.since_point["inside_hits"],
                "outside_hits": self.since_point["outside_hits"],
                "hits": dict(self.since_point["hits"]),
            },
            "streaks": dict(self.streaks),
            "shooter": {
                "hand_lengths": list(self.shooter["hand_lengths"]),
                "longest_hand": self.shooter["longest_hand"],
                "avg_rolls_per_hand": self.shooter["avg_rolls_per_hand"],
                "hand_hist": dict(self.shooter["hand_hist"]),
            },
        }

    def timeline(self, limit: Optional[int] = None) -> List[Dict]:
        """Return recent timeline entries; newest last."""
        if limit is None or limit >= len(self._timeline):
            return list(self._timeline)
        # return the most recent `limit` entries
        return list(self._timeline)[-limit:]