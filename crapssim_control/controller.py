from __future__ import annotations

from typing import Any, Dict, Optional

from .events import derive_event, capture_table_state
from .rules import run_rules_for_event
from .templates import render_template
from .varstore import VarStore
from .telemetry import Telemetry


class ControlStrategy:
    """
    Orchestrates: read table -> derive event -> run rules -> apply intents.
    """

    def __init__(
        self,
        spec: Dict[str, Any],
        telemetry: Optional[Telemetry] = None,
        odds_policy: Optional[str] = None,
    ) -> None:
        self.spec = spec
        # Telemetry: allow None by default; create a disabled Telemetry that writes nowhere.
        # Our Telemetry class requires csv_path; pass None and keep it disabled.
        self.telemetry = telemetry or Telemetry(csv_path=None, enabled=False)
        self.odds_policy = odds_policy
        self.varstore = VarStore.from_spec(spec)

    # Hook called by adapter each roll to (re)stage wagers
    def update_bets(self, table: Any) -> None:
        prev_snapshot = getattr(self, "_prev_state", None)
        curr_snapshot = capture_table_state(table)
        event = derive_event(prev_snapshot, curr_snapshot)

        # Run rules for the derived event
        intents = run_rules_for_event(self.spec, self.varstore, event)

        # Materialize the actions on the live player/table via templates/appliers
        if intents:
            render_template(self.varstore, intents, table, odds_policy=self.odds_policy)

        # Telemetry capture (if enabled)
        if self.telemetry.enabled:
            self.telemetry.record_tick(event=event, varstore=self.varstore, table_snapshot=curr_snapshot)

        # Advance previous snapshot
        self._prev_state = curr_snapshot

    # Optional post-resolution hook (adapter can call this when a bet resolves)
    def after_roll(self, event: Dict[str, Any], table: Any) -> None:
        # Give rules a chance to react to explicit resolution events (e.g., bet_resolved)
        intents = run_rules_for_event(self.spec, self.varstore, event)
        if intents:
            render_template(self.varstore, intents, table, odds_policy=self.odds_policy)
        if self.telemetry.enabled:
            self.telemetry.record_tick(event=event, varstore=self.varstore, table_snapshot=capture_table_state(table))