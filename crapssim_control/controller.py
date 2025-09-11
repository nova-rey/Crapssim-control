# crapssim_control/controller.py
from __future__ import annotations

from typing import Any, Dict, Optional

from .rules import run_rules_for_event, VarStore
from .events import derive_event, capture_table_state
from .materialize import apply_intents
from .telemetry import Telemetry


class ControlStrategy:
    """
    Glue between a JSON spec and the CrapsSim engine.

    The engine is expected to call:
      - update_bets(table) before or after each roll to let us apply rule-driven intents
      - after_roll(table) after outcomes settle (for telemetry, etc.)
    """

    def __init__(
        self,
        spec: Dict[str, Any],
        telemetry: Optional[Telemetry] = None,
        odds_policy: Optional[str] = None,
    ) -> None:
        self.spec = spec
        self.telemetry = telemetry or Telemetry(enabled=False)
        self.vs = VarStore.from_spec(spec)
        # system (table config) will be populated on first update_bets from spec.table
        self.vs.system = {
            "bubble": bool(spec.get("table", {}).get("bubble", False)),
            "table_level": int(spec.get("table", {}).get("level", 5)),
        }
        self.odds_policy = odds_policy or spec.get("table", {}).get("odds_policy")

        # Event derivation snapshots
        self._last_state: Optional[Dict[str, Any]] = None

        # initial mode (optional)
        if "variables" in spec and isinstance(spec["variables"], dict):
            if "mode" in spec["variables"]:
                self.vs.user["mode"] = spec["variables"]["mode"]

    # CrapsSim hook: called around each roll to (re)apply bets per rules
    def update_bets(self, table: Any) -> None:
        curr = capture_table_state(table)
        prev = self._last_state
        event = derive_event(prev, curr)
        self._last_state = curr

        # Feed rules
        intents = run_rules_for_event(self.spec, self.vs, event)

        # Materialize intents on the engine/player
        player = getattr(table, "current_player", None)
        if player is None:
            return  # engine not ready yet (or fake table); no-op
        apply_intents(player, intents, odds_policy=self.odds_policy)

        # Telemetry tracking (lightweight)
        if self.telemetry.enabled:
            self.telemetry.track(event=event, table=table, player=player, vs=self.vs)

    # CrapsSim hook: optional after-settlement callback for additional telemetry
    def after_roll(self, table: Any) -> None:
        if not self.telemetry.enabled:
            return
        player = getattr(table, "current_player", None)
        self.telemetry.track_after_roll(table=table, player=player, vs=self.vs)