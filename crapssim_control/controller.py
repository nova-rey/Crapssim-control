# crapssim_control/controller.py
from __future__ import annotations

from typing import Any, Dict, Optional

# Local imports
from .eval import safe_eval  # noqa: F401
from .templates import render_template  # noqa: F401
from .materialize import apply_intents
from .rules import VarStore, run_rules_for_event
from .events import derive_event
from .tracker import Tracker


class ControlStrategy:
    """
    Glue between a JSON strategy spec and the CrapsSim engine's player interface.
    """

    def __init__(self, spec: Dict[str, Any], telemetry: Any = None, odds_policy: Optional[str] = None):
        self.spec = spec
        self.telemetry = telemetry
        self.odds_policy = odds_policy

        # Var store
        self.vs = VarStore.from_spec(spec)
        table_cfg = spec.get("table", {})
        self.vs.system = {
            "bubble": bool(table_cfg.get("bubble", False)),
            "table_level": int(table_cfg.get("level", 10)),
        }

        # Tracker
        tracking_cfg = (table_cfg.get("tracking") or {})
        self.tracker = Tracker(tracking_cfg)
        self._publish_tracker()

        # Internal bookkeeping
        self._last_bankroll = 0.0
        self._point_before_roll = 0

    def _publish_tracker(self):
        self.vs.system["tracker"] = self.tracker.snapshot()

    def update_bets(self, table: Any) -> None:
        event = derive_event(table)

        if event and event.get("event") == "roll":
            total = int(event.get("total", 0) or 0)
            if total:
                self.tracker.on_roll(total)

        if event and event.get("event") == "point_established":
            p = int(event.get("point", 0) or 0)
            if p:
                self.tracker.on_point_established(p)

        if event and event.get("event") == "seven_out":
            self.tracker.on_seven_out()

        if event and event.get("event") == "shooter_change":
            self.tracker.on_new_shooter()

        if event and event.get("event") == "point_made":
            self.tracker.on_point_made()

        intents = run_rules_for_event(self.spec, self.vs, event or {"event": "roll"})
        apply_intents(
            table.current_player if hasattr(table, "current_player") else self,
            intents,
            odds_policy=self.odds_policy,
        )
        self._publish_tracker()

    def after_roll(self, table: Any) -> None:
        delta = 0.0
        pl = getattr(table, "current_player", None)
        if pl is not None and hasattr(pl, "bankroll_delta"):
            try:
                delta = float(getattr(pl, "bankroll_delta") or 0.0)
            except Exception:
                delta = 0.0

        if delta:
            self.tracker.on_bankroll_delta(delta)

        self._publish_tracker()

    def on_bet_resolved(
        self,
        bet_kind: str,                # e.g., "pass", "dont_pass", "come", "dont_come", "place", "buy", "lay", "field", "hardway", "horn", "any_craps", "any_seven", "prop"
        result: str,                  # "win" | "lose" | "push"
        reason: str = "",             # optional descriptive reason from engine
        number: Optional[int] = None, # box number if applicable (4/5/6/8/9/10) or hardway number (4/6/8/10)
        flat_delta: Optional[float] = None,  # net paid on flat component (>=0 win, <=0 loss)
        odds_delta: Optional[float] = None,  # net paid on odds/lay odds component
        stake_flat: Optional[float] = None,  # amount at risk on flat (optional; for ROI)
        stake_odds: Optional[float] = None,  # amount at risk on odds/lay (optional)
        extra: Optional[Dict[str, Any]] = None,
    ):
        """Engine wrapper can call this per resolved bet to feed aggregates."""
        # Normalize inputs and record
        self.tracker.record_resolution(
            family=bet_kind,
            result=result,
            number=number,
            flat_delta=float(flat_delta or 0.0),
            odds_delta=float(odds_delta or 0.0),
            stake_flat=float(stake_flat or 0.0),
            stake_odds=float(stake_odds or 0.0),
            extra=extra or {"reason": reason} if reason else extra,
        )
        # Keep tracker visible to rules right away
        self._publish_tracker()