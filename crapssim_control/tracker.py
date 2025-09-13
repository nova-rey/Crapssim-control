# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, DefaultDict
from collections import defaultdict

INSIDE_SET = {5, 6, 8, 9}
OUTSIDE_SET = {4, 10}

@dataclass
class _RollState:
    last_roll: Optional[int] = None
    shooter_rolls: int = 0
    rolls_since_point: int = 0
    comeout_rolls: int = 0
    comeout_naturals: int = 0
    comeout_craps: int = 0

@dataclass
class _PointState:
    point: int = 0  # 0 means off

@dataclass
class _BankrollState:
    bankroll: float = 0.0
    bankroll_peak: float = 0.0
    drawdown: float = 0.0
    pnl_since_point: float = 0.0
    # Batch 4 extras (guarded by flag)
    max_drawdown: Optional[float] = None
    recovery_factor: Optional[float] = None

@dataclass
class _SessionState:
    seven_outs: int = 0
    pso: int = 0
    hands: int = 0  # increments on seven-out (shooter change)

@dataclass
class _SincePointState:
    inside_hits: int = 0
    outside_hits: int = 0
    hits: DefaultDict[int, int] = field(default_factory=lambda: defaultdict(int))

class Tracker:
    """
    Game telemetry tracker. All counters are opt-in via config {"enabled": True}.
    Batch-4 adds optional bankroll deep-dive metrics behind config key:
      {"bankroll_extras_enabled": True}
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = config or {}
        self.enabled: bool = bool(cfg.get("enabled", False))

        self.roll = _RollState()
        self.point = _PointState()
        self.bankroll = _BankrollState()
        self.session = _SessionState()
        self.hits: DefaultDict[int, int] = defaultdict(int)
        self.since_point = _SincePointState()

        # Batch-4 feature switch
        self._bankroll_extras_enabled: bool = bool(cfg.get("bankroll_extras_enabled", False))
        self._current_hand_pnl: float = 0.0
        self._pnl_log: List[float] = []  # per-hand deltas, only exposed when extras flag is on

    # -----------------------------
    # Public API (events)
    # -----------------------------
    def on_roll(self, total: int, *, is_comeout: Optional[bool] = None) -> None:
        if not self.enabled:
            return

        self.roll.last_roll = total
        self.hits[total] += 1

        # comeout accounting (derive if not provided)
        comeout = bool(is_comeout) if is_comeout is not None else (self.point.point == 0)

        if comeout:
            self.roll.comeout_rolls += 1
            if total in (7, 11):
                self.roll.comeout_naturals += 1
            if total in (2, 3, 12):
                self.roll.comeout_craps += 1
        else:
            # Only increment rolls_since_point while point is on
            if self.point.point:
                self.roll.rolls_since_point += 1
                # Since-point hit buckets
                if total in INSIDE_SET:
                    self.since_point.inside_hits += 1
                if total in OUTSIDE_SET:
                    self.since_point.outside_hits += 1
                self.since_point.hits[total] += 1

        # Shooter roll count always advances
        self.roll.shooter_rolls += 1

    def on_point_established(self, point: int) -> None:
        if not self.enabled:
            return
        # Set point and reset since-point counters
        self.point.point = point
        self.roll.rolls_since_point = 0
        self.bankroll.pnl_since_point = 0.0
        self._reset_since_point_buckets()

    def on_point_made(self) -> None:
        if not self.enabled:
            return
        # Point turns off, but shooter keeps shooting (same hand).
        self.point.point = 0
        self.roll.rolls_since_point = 0
        self._reset_since_point_buckets()
        # Do NOT finalize hand here.

    def on_seven_out(self) -> None:
        if not self.enabled:
            return
        # PSO detection: seven-out on first roll after point established
        if self.roll.rolls_since_point == 1:
            self.session.pso += 1

        self.session.seven_outs += 1
        self.session.hands += 1

        # Point turns off, new shooter next
        self.point.point = 0
        self.roll.rolls_since_point = 0
        self.roll.shooter_rolls = 0
        self._reset_since_point_buckets()

        # Finalize & log per-hand PnL (Batch-4)
        if self._bankroll_extras_enabled:
            if abs(self._current_hand_pnl) > 0 or True:
                self._pnl_log.append(self._current_hand_pnl)
            self._current_hand_pnl = 0.0

    def on_bankroll_delta(self, delta: float) -> None:
        if not self.enabled:
            return
        self.bankroll.bankroll += float(delta)
        # Track peak and drawdown continuously
        if self.bankroll.bankroll > self.bankroll.bankroll_peak:
            self.bankroll.bankroll_peak = self.bankroll.bankroll
        self.bankroll.drawdown = max(0.0, self.bankroll.bankroll_peak - self.bankroll.bankroll)

        # Attribute to current point cycle
        if self.point.point:
            self.bankroll.pnl_since_point += float(delta)

        # Batch-4: extras
        if self._bankroll_extras_enabled:
            self._current_hand_pnl += float(delta)
            # Max drawdown across the whole run (peak-to-valley)
            current_dd = self.bankroll.drawdown
            if self.bankroll.max_drawdown is None:
                self.bankroll.max_drawdown = current_dd
            else:
                self.bankroll.max_drawdown = max(self.bankroll.max_drawdown, current_dd)

            # Recovery factor: net gain / max_drawdown (if any)
            net_profit = self.bankroll.bankroll  # baseline 0 at start
            if (self.bankroll.max_drawdown or 0.0) > 0.0:
                self.bankroll.recovery_factor = net_profit / self.bankroll.max_drawdown
            else:
                # define as 0.0 when there's no drawdown yet
                self.bankroll.recovery_factor = 0.0

    # -----------------------------
    # Snapshots
    # -----------------------------
    def snapshot(self) -> Dict[str, Any]:
        if not self.enabled:
            return {}
        out = {
            "roll": {
                "last_roll": self.roll.last_roll,
                "shooter_rolls": self.roll.shooter_rolls,
                "rolls_since_point": self.roll.rolls_since_point,
                "comeout_rolls": self.roll.comeout_rolls,
                "comeout_naturals": self.roll.comeout_naturals,
                "comeout_craps": self.roll.comeout_craps,
            },
            "point": {
                "point": self.point.point,
            },
            "bankroll": {
                "bankroll": self.bankroll.bankroll,
                "bankroll_peak": self.bankroll.bankroll_peak,
                "drawdown": self.bankroll.drawdown,
                "pnl_since_point": self.bankroll.pnl_since_point,
            },
            "session": {
                "seven_outs": self.session.seven_outs,
                "pso": self.session.pso,
                "hands": self.session.hands,
            },
            "hits": dict(self.hits),
            "since_point": {
                "inside_hits": self.since_point.inside_hits,
                "outside_hits": self.since_point.outside_hits,
                "hits": dict(self.since_point.hits),
            },
        }

        # Batch-4 extras exposure
        if self._bankroll_extras_enabled:
            out["bankroll"]["max_drawdown"] = self.bankroll.max_drawdown or 0.0
            out["bankroll"]["recovery_factor"] = self.bankroll.recovery_factor or 0.0
            out["bankroll"]["pnl_log"] = list(self._pnl_log)

        return out

    # -----------------------------
    # Helpers
    # -----------------------------
    def _reset_since_point_buckets(self) -> None:
        self.since_point.inside_hits = 0
        self.since_point.outside_hits = 0
        self.since_point.hits.clear()