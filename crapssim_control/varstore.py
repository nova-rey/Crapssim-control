# crapssim_control/varstore.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from .snapshotter import GameState

@dataclass
class VarStore:
    # User variables from SPEC (mutable by rules)
    user: Dict[str, Any] = field(default_factory=dict)
    # System variables (read-only for rules)
    system: Dict[str, Any] = field(default_factory=dict)

    # Internal anchors for PnL/deltas
    _session_start_bankroll: Optional[int] = None
    _shooter_start_bankroll: Optional[int] = None
    _last_shooter_index: Optional[int] = None

    @staticmethod
    def from_spec(spec: dict) -> "VarStore":
        vs = VarStore()
        vs.user = dict(spec.get("variables", {}))
        return vs

    def _maybe_init_session(self, gs: GameState):
        if self._session_start_bankroll is None:
            # GameState already carries starting_bankroll from the engine
            self._session_start_bankroll = int(gs.player.starting_bankroll or gs.player.bankroll)

    def _maybe_update_shooter_anchor(self, gs: GameState):
        """
        Refresh the 'shooter start' bankroll anchor if:
          - first call (anchor None), or
          - we detect a new shooter via derived flag, or
          - shooter index changed (defensive, in case flags differ per engine)
        """
        if self._shooter_start_bankroll is None:
            self._shooter_start_bankroll = int(gs.player.bankroll)
            self._last_shooter_index = int(gs.table.shooter_index)
            return

        # Detect shooter boundary
        new_shooter = bool(gs.is_new_shooter)
        index_changed = (self._last_shooter_index is not None and
                         int(gs.table.shooter_index) != int(self._last_shooter_index))

        if new_shooter or index_changed:
            self._shooter_start_bankroll = int(gs.player.bankroll)
            self._last_shooter_index = int(gs.table.shooter_index)

    def refresh_system(self, gs: GameState):
        """
        Update the read-only system vars based on the latest GameState,
        including bankroll deltas for session and current shooter.
        """
        self._maybe_init_session(gs)
        self._maybe_update_shooter_anchor(gs)

        t = gs.table
        p = gs.player

        # Compute PnL deltas
        session_start = int(self._session_start_bankroll or p.starting_bankroll or p.bankroll)
        shooter_start = int(self._shooter_start_bankroll or p.bankroll)
        pnl_session = int(p.bankroll) - session_start
        pnl_shooter = int(p.bankroll) - shooter_start

        self.system = {
            # table & hand
            "point_on": t.point_on,
            "point": t.point_number,
            "comeout": t.comeout,
            "dice_total": t.dice[2] if t.dice else None,
            "shooter_index": t.shooter_index,
            "roll_index": t.roll_index,
            "rolls_this_shooter": t.rolls_this_shooter,

            # derived flags
            "just_point_established": gs.just_established_point,
            "just_point_made": gs.just_made_point,
            "just_seven_out": gs.just_seven_out,
            "is_new_shooter": gs.is_new_shooter,

            # table rules (set by controller each tick)
            "table_level": t.table_level,
            "bubble": t.bubble,

            # bankroll & deltas
            "bankroll": p.bankroll,
            "session_start_bankroll": session_start,
            "shooter_start_bankroll": shooter_start,
            "pnl_session": pnl_session,
            "pnl_shooter": pnl_shooter,
        }

    def names(self) -> Dict[str, Any]:
        """Merged view (user + system) presented to the expression evaluator."""
        out = dict(self.user)
        out.update(self.system)
        return out