"""
ControlStrategy: bridges SPEC → (events → rules → bet intents) → real bets.

Lifecycle per roll (driven by CrapsSim):
  - update_bets(player): runs BEFORE the dice roll.
      • ensures we have an initial snapshot
      • refreshes system vars from LAST completed roll
      • applies any bet intents computed after the previous roll

  - after_roll(player): runs AFTER the dice roll.
      • snapshots current table/player state
      • updates system vars
      • derives an event (comeout/point_established/roll/seven_out minimal v0)
      • runs rules for that event to compute bet intents for the NEXT tick
"""

from __future__ import annotations

# Base Strategy (fallback class allows import without the engine installed)
try:
    from crapssim.strategy.tools import Strategy  # type: ignore
except Exception:
    class Strategy:  # type: ignore
        def update_bets(self, player): ...
        def completed(self, player): return False
        def after_roll(self, player): ...

from .snapshotter import Snapshotter
from .varstore import VarStore
from .events import derive_event
from .rules import run_rules_for_event
from .materialize import apply_intents


class ControlStrategy(Strategy):
    def __init__(self, spec: dict):
        # Raw SPEC (modes / rules / variables / table config)
        self.spec = spec or {}

        # Last completed-roll snapshot (GameState)
        self.last_state = None

        # Variables: user (mutable) + system (read-only)
        self.vars = VarStore.from_spec(self.spec)

        # Bet intents computed in after_roll() to be applied on the next update_bets()
        self._pending_intents = []  # list[tuple[str, int|None, int]]

        # Stable table rules from SPEC (visible in system vars)
        tbl = self.spec.get("table", {})
        self._bubble = bool(tbl.get("bubble", False))
        self._table_level = int(tbl.get("level", 10))

        # Optional: enable to see events in console during dev
        self.debug_events = False

    # ---- CrapsSim hook: BEFORE roll ----
    def update_bets(self, player):
        # Ensure we have an initial snapshot so rules have context on first tick.
        if self.last_state is None:
            self.last_state = Snapshotter.capture(player.table, player, prev=None)

        # Refresh system vars from the last completed roll; inject table rules
        self.vars.refresh_system(self.last_state)
        self.vars.system["bubble"] = self._bubble
        self.vars.system["table_level"] = self._table_level

        # Apply any bet intents computed after the previous roll
        if self._pending_intents:
            apply_intents(player, self._pending_intents)
            self._pending_intents = []

    # ---- CrapsSim hook: AFTER roll ----
    def after_roll(self, player):
        # Snapshot post-roll state
        curr = Snapshotter.capture(player.table, player, prev=self.last_state)

        # Update system vars to reflect current state; inject table rules
        self.vars.refresh_system(curr)
        self.vars.system["bubble"] = self._bubble
        self.vars.system["table_level"] = self._table_level

        # Derive event from (prev → curr) and run rules → produce bet intents
        event = derive_event(self.last_state, curr)
        if self.debug_events:
            print("EVENT:", event)
        intents = run_rules_for_event(self.spec, self.vars, event)

        # Stash intents for application on NEXT update_bets()
        self._pending_intents = intents

        # Advance window
        self.last_state = curr

    def completed(self, player):
        # Keep running unless the engine decides to stop elsewhere
        return False