"""
ControlStrategy: bridges SPEC → (events → rules → bet intents) → real bets.
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
        self.spec = spec or {}
        self.last_state = None
        self.vars = VarStore.from_spec(self.spec)
        self._pending_intents = []

        tbl = self.spec.get("table", {})
        self._bubble = bool(tbl.get("bubble", False))
        self._table_level = int(tbl.get("level", 10))
        # NEW: odds policy at the table level (default 3-4-5x)
        self._odds_policy = tbl.get("odds_policy", "3-4-5x")

        self.debug_events = False

    def update_bets(self, player):
        if self.last_state is None:
            self.last_state = Snapshotter.capture(player.table, player, prev=None)

        self.vars.refresh_system(self.last_state)
        self.vars.system["bubble"] = self._bubble
        self.vars.system["table_level"] = self._table_level

        if self._pending_intents:
            apply_intents(player, self._pending_intents, odds_policy=self._odds_policy)
            self._pending_intents = []

    def after_roll(self, player):
        curr = Snapshotter.capture(player.table, player, prev=self.last_state)
        self.vars.refresh_system(curr)
        self.vars.system["bubble"] = self._bubble
        self.vars.system["table_level"] = self._table_level

        event = derive_event(self.last_state, curr)
        if self.debug_events:
            print("EVENT:", event)
        intents = run_rules_for_event(self.spec, self.vars, event)
        self._pending_intents = intents
        self.last_state = curr

    def completed(self, player):
        return False