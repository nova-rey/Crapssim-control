from __future__ import annotations

from typing import Any, Dict, Optional, List

from .events import derive_event
from .rules import run_rules_for_event, render_template
from .materialize import apply_intents, BetIntent
from .telemetry import Telemetry
from .varstore import VarStore


class ControlStrategy:
    """
    Orchestrates: snapshot → event → rules → intents → materialization.
    Holds a VarStore for variables, system state, and lightweight tracking.
    """

    def __init__(
        self,
        spec: Dict[str, Any],
        telemetry: Optional[Telemetry] = None,
        odds_policy: Optional[str] = None,
    ) -> None:
        self.spec = spec
        self.telemetry = telemetry or Telemetry(csv_path=None)
        self.odds_policy = odds_policy or (spec.get("table", {}) or {}).get("odds_policy")

        # Variables and system/tracking store
        self.vs = VarStore.from_spec(spec)

        # Cache the last lightweight snapshot for event derivation
        self._prev_snapshot: Optional[Dict[str, Any]] = None

    # -----------------------------
    # Public hooks used by the engine adapter
    # -----------------------------
    def update_bets(self, table: Any) -> None:
        """
        Called by the engine adapter each roll. We:
          1) Take a light snapshot from the table
          2) Derive a high-level event
          3) Update VarStore/system counters based on event
          4) Run rules to get intents
          5) Render/apply intents (materialize bets)
        """
        curr_snapshot = self._snapshot_from_table(table)
        prev_snapshot = self._prev_snapshot

        # Update system side from raw snapshot first (keeps prior test behavior)
        self.vs.refresh_system(curr_snapshot)

        # 2) Event
        event = derive_event(prev_snapshot, curr_snapshot)

        # 3) Tracking side-effects (safe, optional)
        self.vs.apply_event_side_effects(event, curr_snapshot)

        # 4) Run rules engine
        intents = run_rules_for_event(self.spec, self.vs, event)

        # 5) Render a mode template if asked by rules (e.g., apply_template('Main'))
        table_level = (self.spec.get("table") or {}).get("level")
        rendered = render_template(self.spec, self.vs, intents, table_level)

        # 6) Materialize
        apply_intents(table, rendered, odds_policy=self.odds_policy)

        # 7) Telemetry (optional; only if enabled)
        if getattr(self.telemetry, "enabled", False) and hasattr(self.telemetry, "log_roll"):
            self.telemetry.log_roll(curr_snapshot, event, self.vs)

        # 8) Cache snapshot for next roll
        self._prev_snapshot = curr_snapshot

    def after_roll(self, table: Any) -> None:
        """
        Hook after the engine has rolled and settled. Currently a no-op.
        Kept for compatibility and future telemetry/tracking if needed.
        """
        return

    # -----------------------------
    # Snapshot helper (kept simple)
    # -----------------------------
    def _snapshot_from_table(self, table: Any) -> Dict[str, Any]:
        """
        Extract a lightweight, engine-agnostic snapshot from the table.
        Must include fields used by tests and event derivation.
        """
        tv = getattr(table, "view", None) or getattr(table, "table", None) or table

        # Pull dice as (d1, d2, total) if possible
        dice = getattr(tv, "dice", None)
        if isinstance(dice, (tuple, list)) and len(dice) >= 2:
            if len(dice) == 2:
                d1, d2 = dice
                total = (int(d1) + int(d2)) if all(isinstance(x, int) for x in (d1, d2)) else None
                dice_tuple = (d1, d2, total)
            else:
                dice_tuple = tuple(dice[:3])
        else:
            dice_tuple = None

        # Build a plain dict view
        snap = {
            "comeout": bool(getattr(tv, "comeout", True)),
            "point_on": bool(getattr(tv, "point_on", False)),
            "point_number": getattr(tv, "point_number", None),
            "dice": dice_tuple,
            "shooter_index": getattr(tv, "shooter_index", 0),
            "roll_index": getattr(tv, "roll_index", 0),
        }

        # If player/bankroll exists on table, include it for delta telemetry
        player = getattr(table, "player", None) or getattr(tv, "player", None)
        if player is not None:
            snap["bankroll"] = getattr(player, "bankroll", None)

        return snap