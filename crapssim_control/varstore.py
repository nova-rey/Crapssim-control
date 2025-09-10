from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any
from .snapshotter import GameState

@dataclass
class VarStore:
    # User variables from SPEC (mutable by rules)
    user: Dict[str, Any] = field(default_factory=dict)
    # System variables (read-only for rules)
    system: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_spec(spec: dict) -> "VarStore":
        vs = VarStore()
        vs.user = dict(spec.get("variables", {}))
        return vs

    def refresh_system(self, gs: GameState):
        t = gs.table; p = gs.player
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

            # table rules (from strategy config later; placeholders live in snapshotter)
            "table_level": t.table_level,
            "bubble": t.bubble,

            # bankroll
            "bankroll": p.bankroll,
        }

    def names(self) -> Dict[str, Any]:
        # Merge view presented to expression evaluator
        out = dict(self.user)
        out.update(self.system)
        return out