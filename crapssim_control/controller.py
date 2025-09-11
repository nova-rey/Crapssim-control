from __future__ import annotations

from typing import Any, Dict, Optional

from .events import derive_event
from .templates import render_template
from .materialize import apply_intents
from .rules import run_rules_for_event
from .varstore import VarStore
from .telemetry import Telemetry


class ControlStrategy:
    """
    Orchestrates:
      - VarStore state
      - per-roll table snapshot
      - event derivation
      - rule evaluation -> intents
      - template rendering -> concrete bet intents
      - applying intents to the player
    """

    def __init__(
        self,
        spec: Dict[str, Any],
        telemetry: Optional[Telemetry] = None,
        odds_policy: Optional[str] = None,
    ) -> None:
        self.spec = spec
        # Provide a benign Telemetry; empty path keeps tests happy (mkdirs on ".")
        self.telemetry = telemetry or Telemetry(csv_path="")

        self.vs = VarStore.from_spec(spec)

        tbl = spec.get("table", {}) if isinstance(spec, dict) else {}
        self.table_level: int = int(tbl.get("level", 10))
        self.odds_policy = odds_policy if odds_policy is not None else tbl.get("odds_policy")

        self._prev_snapshot: Optional[Dict[str, Any]] = None

    # --- lifecycle hooks expected by tests ---

    def update_bets(self, table: Any) -> None:
        """
        Called by the engine adapter each roll.
        """
        curr_snapshot = self._snapshot_from_table(table)
        prev_snapshot = self._prev_snapshot

        event = derive_event(prev_snapshot, curr_snapshot)

        # rules -> high-level intents
        intents = run_rules_for_event(self.spec, self.vs, event)

        # template rendering -> concrete bet intents
        rendered = render_template(self.spec, self.vs, intents, table_level=self.table_level)

        # Apply to the first/only player on the table.
        player = self._first_player(table)
        if player is not None:
            apply_intents(player, rendered, odds_policy=self.odds_policy)

        # Bookkeeping for next roll and optional hook
        self._prev_snapshot = curr_snapshot
        # Call with both args; EngineAdapter may call with only table (handled by default below).
        self.after_roll(table, event)

    def after_roll(self, table: Any, event: Optional[Dict[str, Any]] = None) -> None:
        """No-op hook (event is optional so EngineAdapter(table) call works)."""
        return None

    # --- helpers ---

    def _first_player(self, table: Any):
        """
        Return the first player object registered on the table, if any.
        Works with the test fakes that expose `add_player()` and `players`.
        """
        players = getattr(table, "players", None)
        if players is None and isinstance(table, dict):
            players = table.get("players")
        if players and len(players) > 0:
            return players[0]
        single = getattr(table, "player", None)
        if single is None and isinstance(table, dict):
            single = table.get("player")
        return single

    def _snapshot_from_table(self, table: Any) -> Dict[str, Any]:
        """
        Take a light snapshot compatible with derive_event().
        """
        def g(obj, name, default=None):
            if isinstance(obj, dict):
                return obj.get(name, default)
            return getattr(obj, name, default)

        table_view = getattr(table, "view", table)

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