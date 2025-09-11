# crapssim_control/tracker.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, Optional


DEFAULT_TRACKING_CFG = {
    "enabled": False,
    "scopes": ["session"],              # "session", "shooter"
    "bets": [],                         # families to aggregate (Phase B)
    "by_number": [],                    # families to split by number (Phase B)
    "reset_shooter_on": "seven_out",    # or "point_resolved"
    "roll_hits": True,                  # maintain hit_counts[2..12]
    "bankroll": True,                   # maintain peak/drawdown
    "odds_breakout": True,              # separate flat vs odds (Phase B)
    "ledger": False                     # detailed per-resolution CSV (Phase C)
}


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    out.update(b or {})
    return out


@dataclass
class Tracker:
    """Lightweight session/shooter/roll/point/bankroll tracker.

    Phase A:
      - roll: last_roll, roll_index, shooter_rolls, rolls_since_point
      - point: point, point_cycle
      - bankroll: bankroll, bankroll_peak, drawdown, max_drawdown, pnl_since_shooter, pnl_since_point
      - hits: hit_counts[2..12] (+ convenience aliases via dict access)
    """
    cfg: Dict[str, Any] = field(default_factory=dict)

    # roll scope
    last_roll: int = 0
    roll_index: int = 0
    shooter_rolls: int = 0
    rolls_since_point: int = 0

    # point scope
    point: int = 0  # 0/None means off
    point_cycle: int = 0

    # bankroll scope
    bankroll: float = 0.0
    bankroll_peak: float = 0.0
    drawdown: float = 0.0
    max_drawdown: float = 0.0
    pnl_since_shooter: float = 0.0
    pnl_since_point: float = 0.0

    # hits
    hit_counts: Dict[int, int] = field(default_factory=lambda: {n: 0 for n in range(2, 13)})

    # shooter/session indices
    shooter_index: int = 1
    shooter_count: int = 0
    hands_played: int = 0
    seven_outs: int = 0
    points_made: int = 0

    def __post_init__(self):
        # normalize config
        self.cfg = _merge(DEFAULT_TRACKING_CFG, self.cfg or {})
        # ensure sensible types
        self.point = int(self.point or 0)

    # ---- Serialization to vs.system["tracker"] ----

    def snapshot(self) -> Dict[str, Any]:
        """Return a dict suitable for storing in VarStore.system['tracker']."""
        return {
            "roll": {
                "last_roll": self.last_roll,
                "roll_index": self.roll_index,
                "shooter_rolls": self.shooter_rolls,
                "rolls_since_point": self.rolls_since_point,
            },
            "point": {
                "point": self.point or 0,
                "point_cycle": self.point_cycle,
            },
            "bankroll": {
                "bankroll": self.bankroll,
                "bankroll_peak": self.bankroll_peak,
                "drawdown": self.drawdown,
                "max_drawdown": self.max_drawdown,
                "pnl_since_shooter": self.pnl_since_shooter,
                "pnl_since_point": self.pnl_since_point,
            },
            "hits": dict(self.hit_counts),
            "shooter": {
                "shooter_index": self.shooter_index,
                "shooter_rolls": self.shooter_rolls,
            },
            "session": {
                "shooter_count": self.shooter_count,
                "hands_played": self.hands_played,
                "seven_outs": self.seven_outs,
                "points_made": self.points_made,
            },
            "config": dict(self.cfg),
        }

    # ---- Event hooks (call from controller) ----

    def on_new_shooter(self):
        """Call when the shooter changes at table level."""
        self.shooter_count += 1
        # The new active shooter index:
        self.shooter_index = self.shooter_count + 1  # if we increment after previous finishes
        # Reset per-shooter counters:
        self.shooter_rolls = 0
        self.pnl_since_shooter = 0.0
        # rolls_since_point will be reset when a new point is established
        # point remains whatever table has (usually off on comeout)

    def on_roll(self, total: int):
        """Call every dice roll, provide 2..12."""
        self.last_roll = int(total)
        self.roll_index += 1
        self.shooter_rolls += 1
        if self.point:
            self.rolls_since_point += 1
        if self.cfg.get("roll_hits", True) and 2 <= total <= 12:
            self.hit_counts[total] = self.hit_counts.get(total, 0) + 1

    def on_point_established(self, p: int):
        """Call when a point is set (4/5/6/8/9/10)."""
        self.point = int(p)
        self.rolls_since_point = 0

    def on_point_made(self):
        """Call when the point is made (resolved as a win for line)."""
        self.points_made += 1
        # Depending on rules, shooter continues; point turns off until next comeout
        self.point = 0
        self.rolls_since_point = 0
        if self.cfg.get("reset_shooter_on") == "point_resolved":
            self._reset_for_new_shooter_context()

    def on_seven_out(self):
        """Call when a seven-out occurs (hand ends)."""
        self.seven_outs += 1
        self.point = 0
        self.rolls_since_point = 0
        self.hands_played += 1  # completed shooter/hand
        self._reset_for_new_shooter_context()

    def _reset_for_new_shooter_context(self):
        # End current shooter and start next
        self.shooter_count += 1
        self.shooter_index = self.shooter_count + 1
        self.shooter_rolls = 0
        self.pnl_since_shooter = 0.0
        # point off; will reset again upon establishment

    def on_bankroll_delta(self, delta: float):
        """Call whenever bankroll changes (net of a roll)."""
        if not self.cfg.get("bankroll", True):
            return
        self.bankroll += float(delta)
        if self.bankroll > self.bankroll_peak:
            self.bankroll_peak = self.bankroll
        self.drawdown = max(0.0, self.bankroll_peak - self.bankroll)
        if self.drawdown > self.max_drawdown:
            self.max_drawdown = self.drawdown

        # contextual PnL
        self.pnl_since_shooter += float(delta)
        if self.point:
            self.pnl_since_point += float(delta)

    def on_point_cleared(self):
        """Call when point turns off with no explicit 'made' (e.g., seven-out already handled)."""
        self.point = 0
        self.rolls_since_point = 0
        self.pnl_since_point = 0.0