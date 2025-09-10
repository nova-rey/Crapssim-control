try:
    from crapssim.strategy.tools import Strategy
except Exception:
    class Strategy:  # fallback for editing
        def update_bets(self, player): ...
        def completed(self, player): return False
        def after_roll(self, player): ...

from .snapshotter import Snapshotter
from .varstore import VarStore
from .events import derive_event
from .rules import run_rules_for_event

class ControlStrategy(Strategy):
    """v0 scaffold: capture snapshots and run rules → produce bet intents (not yet materialized)."""
    def __init__(self, spec: dict):
        self.spec = spec or {}
        self.last_state = None
        self.vars = VarStore.from_spec(self.spec)
        self._pending_intents = []  # type: list

        # Table rules from SPEC so system view knows table config on first tick
        tbl = self.spec.get("table", {})
        self._bubble = bool(tbl.get("bubble", False))
        self._table_level = int(tbl.get("level", 10))

    def update_bets(self, player):
        # Ensure initial snapshot exists
        if self.last_state is None:
            self.last_state = Snapshotter.capture(player.table, player, prev=None)

        # Refresh system vars from *last* completed roll
        self.vars.refresh_system(self.last_state)
        # (ensure table rules visibility before first after_roll)
        self.vars.system["bubble"] = self._bubble
        self.vars.system["table_level"] = self._table_level

        # Materialization of intents to real bets will come in the next step.
        # For now, we just clear any previous intents so we don't replay them.
        self._pending_intents = []

    def after_roll(self, player):
        # Snapshot current post-roll state
        curr = Snapshotter.capture(player.table, player, prev=self.last_state)
        # Update system variables to reflect the new state
        self.vars.refresh_system(curr)
        self.vars.system["bubble"] = self._bubble
        self.vars.system["table_level"] = self._table_level

        # Derive event and run rules → produce bet intents to apply next tick
        event = derive_event(self.last_state, curr)
        intents = run_rules_for_event(self.spec, self.vars, event)
        self._pending_intents = intents

        # Move window forward
        self.last_state = curr

    def completed(self, player):
        return False