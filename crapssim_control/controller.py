from __future__ import annotations

from typing import Any, Dict, Optional

from .events import derive_event
from .templates import render_template
from .materialize import apply_intents
from .runner import run_rules_for_event
from .vars import VarStore
from .telemetry import Telemetry


class ControlStrategy:
    """
    Thin orchestrator that:
      - keeps a VarStore
      - snapshots the table each roll
      - derives a coarse event
      - runs rules to produce intents
      - renders a mode template into concrete bet intents
      - applies intents to the table/player
    """

    def __init__(
        self,
        spec: Dict[str, Any],
        telemetry: Optional[Telemetry] = None,
        odds_policy: Optional[str] = None,
    ) -> None:
        self.spec = spec
        # Telemetry default: provide a benign instance that won’t write anywhere.
        # Telemetry(csv_path="") is safe (dirname("") -> ".", mkdirs ok; tests don’t write).
        self.telemetry = telemetry or Telemetry(csv_path="")
        self.vs = VarStore.from_spec(spec)

        # Cache a table-level for template rendering; fall back to 10 if absent.
        tbl = spec.get("table", {}) if isinstance(spec, dict) else {}
        self.table_level: int = int(tbl.get("level", 10))
        self.odds_policy = odds_policy if odds_policy is not None else tbl.get("odds_policy")

        # Remember previous light snapshot for derive_event
        self._prev_snapshot: Optional[Dict[str, Any]] = None

    # --- lifecycle hooks expected by tests ---

    def update_bets(self, table: Any) -> None:
        """
        Called by the engine adapter each roll.
        """
        curr_snapshot = self._snapshot_from_table(table)
        prev_snapshot = self._prev_snapshot

        event = derive_event(prev_snapshot, curr_snapshot)

        # Rules -> high-level intents
        intents = run_rules_for_event(self.spec, self.vs, event)

        # Render any referenced mode templates into concrete bet intents
        rendered = render_template(self.spec, self.vs, intents, table_level=self.table_level)

        # APPLY: (player first, intents second). We passed these reversed earlier.
        apply_intents(table, rendered, odds_policy=self.odds_policy)

        # Bookkeeping for next roll + telemetry hook
        self._prev_snapshot = curr_snapshot
        self.after_roll(table, event)

    def after_roll(self, table: Any, event: Dict[str, Any]) -> None:
        """
        Existence required by tests; keep as a no-op hook for now.
        Strategies could persist telemetry, adjust vars, etc.
        """
        return None

    # --- helpers ---

    def _snapshot_from_table(self, table: Any) -> Dict[str, Any]:
        """
        Take a light snapshot compatible with derive_event().
        We only read what the tests and derive_event need: comeout, point flags/numbers, and roll index.
        """
        # Try to be tolerant to both attribute- and dict-style tables.
        def g(obj, name, default=None):
            if isinstance(obj, dict):
                return obj.get(name, default)
            return getattr(obj, name, default)

        table_view = getattr(table, "view", table)  # some fakes may expose fields directly

        # comeout can be top-level or nested; record both shapes that our derive_event accepts.
        comeout = g(table_view, "comeout", False)

        snapshot = {
            "comeout": bool(comeout),
            "table": {"comeout": bool(comeout)},
            "point_number": g(table_view, "point_number", None),
            "just_established_point": g(table_view, "just_established_point", False),
            "just_made_point": g(table_view, "just_made_point", False),
            "roll_index": g(table_view, "roll_index", None),
        }
        return snapshot