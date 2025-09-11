# crapssim_control/controller.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .telemetry import Telemetry
from .varstore import VarStore
from .rules import run_rules_for_event
from .events import derive_event, capture_table_state
from .templates import render_template  # kept for future use (not required by tests)
from .materialize import apply_intents  # exported API (tests import from materialize directly)


class ControlStrategy:
    """
    Thin wrapper that:
      - holds the JSON spec and a VarStore
      - derives events from the engine's table snapshots
      - runs the rules engine to produce "intents"
      - (optionally) records telemetry

    The EngineAdapter may call:
      - update_bets(table): compute intents for the current tick (safe no-op if none)
      - after_roll(table): hook after a roll resolves (safe no-op)
      - after_shooter_change(table): hook when shooter rotates (safe no-op)
    """

    def __init__(
        self,
        spec: Dict[str, Any],
        telemetry: Optional[Telemetry] = None,
        odds_policy: Optional[str] = None,
    ) -> None:
        self.spec = spec
        self.telemetry = telemetry or Telemetry()
        # be tolerant if Telemetry exposes an 'enabled' switch
        if hasattr(self.telemetry, "enabled"):
            setattr(self.telemetry, "enabled", False)

        self.odds_policy = odds_policy or self.spec.get("table", {}).get("odds_policy")
        self.vs = VarStore.from_spec(self.spec)

        # seed system vars used by legalization/template math
        table = self.spec.get("table", {})
        self.vs.system = {
            "bubble": bool(table.get("bubble", False)),
            "table_level": int(table.get("level", 10)),
        }

        self._prev_snapshot: Optional[Dict[str, Any]] = None
        self.latest_event: Optional[Dict[str, Any]] = None
        self.latest_intents: List[Tuple[str, Optional[int], float, Dict[str, Any]]] = []

    # ---------- public hooks expected by adapter/tests -----------

    def update_bets(self, table: Any) -> None:
        """
        Observe table, derive a high-level event, run rules, and cache intents.
        EngineAdapter decides when/how to materialize these against a player.
        """
        curr = capture_table_state(table)
        ev = derive_event(self._prev_snapshot, curr)
        self.latest_event = ev

        # run rules → intents (list of (kind, number|None, amount, extras))
        intents = run_rules_for_event(self.spec, self.vs, ev)
        self.latest_intents = intents

        # record lightweight telemetry if enabled
        if getattr(self.telemetry, "enabled", False) and hasattr(self.telemetry, "log_tick"):
            try:
                self.telemetry.log_tick(event=ev, intents=intents, vars=self.vs.snapshot())
            except Exception:
                # Never allow telemetry to crash gameplay
                pass

        # advance snapshot
        self._prev_snapshot = curr

    def after_roll(self, table: Any) -> None:
        """
        Optional hook after a roll resolves. Safe no-op; we just ensure the
        previous snapshot is current so next call can compute transitions.
        """
        self._prev_snapshot = capture_table_state(table)

    def after_shooter_change(self, table: Any) -> None:
        """
        Optional hook on shooter rotation. Safe no-op for now.
        Strategies may choose to reset shooter-scoped variables here later.
        """
        # Intentionally minimal; keep snapshot fresh.
        self._prev_snapshot = capture_table_state(table)

    # ---------- convenience getters (not required, handy for adapters) -----------

    def pop_latest_intents(self) -> List[Tuple[str, Optional[int], float, Dict[str, Any]]]:
        out = self.latest_intents
        self.latest_intents = []
        return out