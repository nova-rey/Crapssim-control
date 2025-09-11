# crapssim_control/controller.py
from __future__ import annotations

from typing import Any, Dict, Optional

# Local imports
from .eval import safe_eval  # noqa: F401 (used by rules via VarStore)
from .templates import render_template  # noqa: F401 (kept for completeness / future use)
from .materialize import apply_intents
from .rules import VarStore, run_rules_for_event
from .events import derive_event
from .tracker import Tracker


class ControlStrategy:
    """
    Glue between a JSON strategy spec and the CrapsSim engine's player interface.
    Responsibilities:
      - Hold variables/state (VarStore)
      - Evaluate rules on events to produce intents
      - Legalize & apply intents to engine bet objects
      - Maintain tracker counters (roll/point/bankroll/etc.)
      - Optional telemetry (handled elsewhere)
    """

    def __init__(self, spec: Dict[str, Any], telemetry: Any = None, odds_policy: Optional[str] = None):
        self.spec = spec
        self.telemetry = telemetry
        self.odds_policy = odds_policy

        # Var store
        self.vs = VarStore.from_spec(spec)
        table_cfg = spec.get("table", {})
        # System defaults needed by legalizer/templates
        self.vs.system = {
            "bubble": bool(table_cfg.get("bubble", False)),
            "table_level": int(table_cfg.get("level", 10)),
        }

        # Tracker (Phase A)
        tracking_cfg = (table_cfg.get("tracking") or {})
        self.tracker = Tracker(tracking_cfg)
        # Publish initial snapshot so rules can read tracker immediately
        self._publish_tracker()

        # Internal bookkeeping
        self._last_bankroll = 0.0  # baseline; engine may not expose bankroll--this is deltas only
        self._point_before_roll = 0

    # ---- Helper to expose tracker into VarStore.system ----
    def _publish_tracker(self):
        self.vs.system["tracker"] = self.tracker.snapshot()

    # ---- Engine-facing hooks (names may vary across CrapsSim versions) ----

    def update_bets(self, table: Any) -> None:
        """Called by engine each cycle/roll to (re)apply bets based on rules."""
        # Derive event from table state
        event = derive_event(table)

        # Update tracker pre-rule if roll known
        if event and event.get("event") == "roll":
            total = int(event.get("total", 0) or 0)
            if total:
                self.tracker.on_roll(total)

        # Point changes
        if event and event.get("event") == "point_established":
            p = int(event.get("point", 0) or 0)
            if p:
                self.tracker.on_point_established(p)

        if event and event.get("event") == "seven_out":
            self.tracker.on_seven_out()

        if event and event.get("event") == "shooter_change":
            self.tracker.on_new_shooter()

        if event and event.get("event") == "point_made":
            # Optional explicit event if engine exposes it
            self.tracker.on_point_made()

        # Run rules → intents
        intents = run_rules_for_event(self.spec, self.vs, event or {"event": "roll"})

        # Apply intents to engine
        apply_intents(
            table.current_player if hasattr(table, "current_player") else self,
            intents,
            odds_policy=self.odds_policy,
        )

        # Publish tracker for rule visibility
        self._publish_tracker()

    # Some engines call after_roll / afterResolve; keep both if available

    def after_roll(self, table: Any) -> None:
        """Called after dice are resolved; compute bankroll deltas and refresh tracker snapshot."""
        # If the engine exposes bankroll delta for the player, capture it.
        delta = 0.0
        # Try common patterns:
        pl = getattr(table, "current_player", None)
        if pl is not None and hasattr(pl, "bankroll_delta"):
            try:
                delta = float(getattr(pl, "bankroll_delta") or 0.0)
            except Exception:
                delta = 0.0

        if delta:
            self.tracker.on_bankroll_delta(delta)

        # Publish tracker after updates
        self._publish_tracker()

    # Compatibility: some engines call this on each bet resolution
    def on_bet_resolved(
        self,
        bet_kind: str,
        result: str,
        reason: str = "",
        number: Optional[int] = None,
        amount: Optional[float] = None,
    ):
        """Optional callback from engine strategy wrapper; reserved for Phase B/C aggregation."""
        # Phase A uses bankroll deltas at roll boundary; Phase B will consume this more deeply.
        pass