"""
varstore.py -- minimal variable store with system counters.

Adds robust initialization for session/shooter P&L fields expected by tests:
- session_start_bankroll
- shooter_start_bankroll
- pnl_session
- pnl_shooter

Also keeps existing behavior for rolls_since_point tracking if present upstream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


def _get(d: Dict[str, Any], k: str, default=None):
    return d.get(k, default) if isinstance(d, dict) else default


@dataclass
class VarStore:
    variables: Dict[str, Any] = field(default_factory=dict)
    system: Dict[str, Any] = field(default_factory=dict)
    counters: Dict[str, Any] = field(default_factory=dict)
    _last_bankroll: Optional[float] = None

    # ---------- Construction ----------

    @classmethod
    def from_spec(cls, spec: Dict[str, Any]) -> "VarStore":
        vs = cls()
        vs.variables = dict(spec.get("variables", {}))
        vs.system = {}
        vs.counters = {
            "number_hits": {4: 0, 5: 0, 6: 0, 8: 0, 9: 0, 10: 0},
            "number_losses": {4: 0, 6: 0, 8: 0, 10: 0},
            "points_established": 0,
            "points_made": 0,
            "seven_outs": 0,
        }
        return vs

    # ---------- System refresh from snapshot ----------

    def refresh_system(self, snapshot: Any) -> None:
        """
        Update system dictionary from a lightweight snapshot shape used in tests.

        Snapshot schema (dict form, fields optional):
        {
          "table": {
             "comeout": bool,
             "point_on": bool,
             "point_number": int|None,
             "roll_index": int,
             "shooter_index": int|None,
             "is_new_shooter": bool|None,
          },
          "player": {
             "bankroll": float|int,
             "starting": float|int,   # session starting bankroll (if provided)
          }
        }
        """
        # --- pull table / player bits robustly ---
        tbl = snapshot.get("table", {}) if isinstance(snapshot, dict) else {}
        ply = snapshot.get("player", {}) if isinstance(snapshot, dict) else {}

        bankroll = _get(ply, "bankroll", _get(snapshot, "bankroll"))
        starting = _get(ply, "starting", _get(snapshot, "starting"))
        is_new_shooter = bool(_get(tbl, "is_new_shooter", False))
        shooter_index = _get(tbl, "shooter_index")

        comeout = bool(_get(tbl, "comeout", False))
        point_on = bool(_get(tbl, "point_on", False))
        point_num = _get(tbl, "point_number")

        # Initialize defaults if absent
        if "session_start_bankroll" not in self.system:
            # Prefer explicit "starting" if provided; otherwise use first seen bankroll
            if starting is not None:
                self.system["session_start_bankroll"] = float(starting)
            elif bankroll is not None:
                self.system["session_start_bankroll"] = float(bankroll)

        if "shooter_start_bankroll" not in self.system and bankroll is not None:
            self.system["shooter_start_bankroll"] = float(bankroll)

        if "pnl_session" not in self.system:
            self.system["pnl_session"] = 0.0
        if "pnl_shooter" not in self.system:
            self.system["pnl_shooter"] = 0.0

        # Shooter transitions
        if is_new_shooter and bankroll is not None:
            # Reset shooter baseline on new shooter
            self.system["shooter_start_bankroll"] = float(bankroll)
            self.system["pnl_shooter"] = 0.0

        # Maintain rolls_since_point
        prev_rsp = int(self.system.get("rolls_since_point", 0) or 0)
        if comeout and not point_on:
            # At comeout (no point on), zero it
            self.system["rolls_since_point"] = 0
        elif point_on:
            # If a point is on, increment unless this snapshot looks like immediate establishment.
            # Heuristic: if previous was 0 or point has just changed (set elsewhere), keep 0; otherwise +1
            # (Test behavior: first roll under a point should produce 0, next → 1)
            # We cannot see the "previous" snapshot here, so we treat transition via controller/tests.
            # If rsp already exists and point_on, increment for non-comeout snapshots.
            self.system["rolls_since_point"] = prev_rsp + (0 if prev_rsp == 0 and comeout else 1)

        # Store current point number for reference
        self.system["point_number"] = point_num if point_on else None
        self.system["comeout"] = comeout

        # Shooter index (if provided)
        if shooter_index is not None:
            self.system["shooter_index"] = shooter_index

        # P&L
        if bankroll is not None:
            start_session = float(self.system.get("session_start_bankroll", bankroll))
            start_shooter = float(self.system.get("shooter_start_bankroll", bankroll))
            self.system["pnl_session"] = float(bankroll) - start_session
            self.system["pnl_shooter"] = float(bankroll) - start_shooter

        # Keep last bankroll for potential future diffs
        if bankroll is not None:
            self._last_bankroll = float(bankroll)