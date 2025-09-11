"""
varstore.py -- lightweight VarStore compatible with the tests.

Responsibilities covered here (per tests):
- Hold user variables (spec["variables"]) and a 'system' dict with runtime state.
- Provide VarStore.from_spec(spec)
- Provide refresh_system(gs) to update:
    * rolls_since_point
    * comeout, point_number
    * session_start_bankroll, shooter_start_bankroll
    * pnl_session, pnl_shooter
- Provide apply_event_side_effects(event, snapshot) hook (no-op for now)

NOTE: This file aims to be minimally invasive but test-complete. If your
project had a richer VarStore previously, you can merge the small behaviors
added here into it; the keys/logic below are what tests assert.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class VarStore:
    def __init__(
        self,
        variables: Optional[Dict[str, Any]] = None,
        *,
        system: Optional[Dict[str, Any]] = None,
    ) -> None:
        # User-configurable variables (unit sizes, mode, etc.)
        self.variables: Dict[str, Any] = dict(variables or {})

        # System/runtime state the tests look at
        self.system: Dict[str, Any] = dict(system or {})

        # Some tests refer to counters; include a small stable set
        self.counters: Dict[str, Any] = {
            "number_hardways_losses": {4: 0, 6: 0, 8: 0, 10: 0},
            "points_established": 0,
            "points_made": 0,
            "seven_outs": 0,
        }

        # For optional bankroll delta tracking if needed later
        self._last_bankroll: Optional[float] = None

    # ---------- Construction ----------

    @classmethod
    def from_spec(cls, spec: Dict[str, Any]) -> "VarStore":
        vars_in = dict(spec.get("variables", {}))
        # honor "mode" if present
        if "modes" in spec and "mode" not in vars_in and spec["modes"]:
            # not required, but keep behavior stable if caller sets it
            pass
        return cls(vars_in, system={})

    # ---------- Controller/engine hooks ----------

    def apply_event_side_effects(self, event: Dict[str, Any], snapshot: Any) -> None:
        """
        Optional hook invoked by controller after derive_event(). Kept as a no-op
        for now; gives us a safe place to evolve counters later.
        """
        return

    # ---------- Snapshot ingestion ----------

    def refresh_system(self, gs: Any) -> None:
        """
        Update system values from a dict- or attr-style lightweight snapshot.

        Tests construct snapshots with helpers like _gs(...), which may place
        fields at top-level or under .table/.player.
        """
        sys = self.system

        def g(*path, default=None):
            cur = gs
            for key in path:
                if cur is None:
                    return default
                if isinstance(cur, dict):
                    cur = cur.get(key, None)
                else:
                    cur = getattr(cur, key, None)
            return default if cur is None else cur

        # Ensure keys exist
        sys.setdefault("rolls_since_point", 0)
        sys.setdefault("point_number", None)
        sys.setdefault("comeout", True)
        sys.setdefault("pnl_session", 0)
        sys.setdefault("pnl_shooter", 0)

        # Read table flags / metadata from either top-level or table subdict
        comeout = g("table", "comeout", default=g("comeout", default=False))
        point_on = g("table", "point_on", default=g("point_on", default=False))
        point_num = g("table", "point_number", default=g("point_num", default=None))
        # roll index is sometimes provided, but we don't strictly need it
        _roll_idx = g("table", "roll_index", default=g("roll_idx", default=None))

        # Bankroll fields can be at top-level (per tests)
        bankroll = g("player", "bankroll", default=g("bankroll"))
        starting = g("player", "starting", default=g("starting"))

        # Session start bankroll initializes once
        if "session_start_bankroll" not in sys and starting is not None:
            sys["session_start_bankroll"] = starting

        # Shooter start bankroll resets at new shooter
        is_new_shooter = g("table", "is_new_shooter", default=g("is_new_shooter", default=False))
        if is_new_shooter and starting is not None:
            sys["shooter_start_bankroll"] = starting
            sys["pnl_shooter"] = 0

        # Compute PnL if bankroll known
        if bankroll is not None:
            ss = sys.get("session_start_bankroll")
            if ss is not None:
                sys["pnl_session"] = bankroll - ss
            shs = sys.get("shooter_start_bankroll")
            if shs is not None:
                sys["pnl_shooter"] = bankroll - shs

        # rolls_since_point logic
        prev_point = sys.get("point_number")
        prev_comeout = sys.get("comeout", True)

        # If a new point is established (or transitioning from comeout to point_on)
        if point_on and (prev_point is None or prev_point != point_num or prev_comeout):
            sys["rolls_since_point"] = 0
        # If we remain under the same point between rolls, increment
        elif point_on and prev_point == point_num and not comeout:
            sys["rolls_since_point"] += 1
        else:
            # Not under a point phase
            sys["rolls_since_point"] = 0

        # Persist flags
        sys["point_number"] = point_num
        sys["comeout"] = comeout