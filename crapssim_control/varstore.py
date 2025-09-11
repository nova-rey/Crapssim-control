from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


def _get_dictlike(obj: Any, key: str, default: Any = None) -> Any:
    """
    Read attribute or dict key with the same name.
    - If `obj` has attribute `key`, return it.
    - Else if `obj` is a dict, return obj.get(key, default).
    - Else default.
    """
    if obj is None:
        return default
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def _coerce_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)
    except Exception:
        return None


@dataclass
class VarStore:
    """
    Holds user-tunable variables, derived system values, and simple counters.
    Tests expect:
      - vs.variables: dict of user variables
      - vs.user: alias to vs.variables (so rules can read/mutate)
      - vs.system: dictionary of derived state like pnl_session, rolls_since_point, etc.
      - methods: from_spec(...), refresh_system(snapshot), apply_event_side_effects(...)
    """
    variables: Dict[str, Any] = field(default_factory=dict)
    system: Dict[str, Any] = field(default_factory=dict)
    counters: Dict[str, Any] = field(default_factory=dict)
    user: Dict[str, Any] = field(default_factory=dict)  # alias to variables
    _last_bankroll: Optional[float] = None

    # --- constructors ---------------------------------------------------------

    @classmethod
    def from_spec(cls, spec: Dict[str, Any]) -> "VarStore":
        variables = dict(spec.get("variables", {}))
        vs = cls(variables=variables)
        # Alias user -> variables so test code can read vs.user["units"]
        vs.user = vs.variables
        # Seed some counters that tests may read or increment later
        vs.counters = {
            "number_frequencies": {n: 0 for n in range(2, 13)},
            "point_losses": {4: 0, 6: 0, 8: 0, 10: 0},
            "points_established": 0,
            "points_made": 0,
            "seven_outs": 0,
        }
        return vs

    # --- public api -----------------------------------------------------------

    def refresh_system(self, snapshot: Any) -> None:
        """
        Update derived system state from a table/player snapshot.

        Supports both dict-shaped snapshots and the tests' dataclasses:
          GameState(table=TableView(...), player=PlayerView(...), is_new_shooter=bool, ...)
        """
        # table/player sections (accept dict-like or attribute-style)
        tbl = _get_dictlike(snapshot, "table", {}) or {}
        ply = _get_dictlike(snapshot, "player", {}) or {}

        # --- Basic table state
        comeout = bool(_get_dictlike(tbl, "comeout", False))
        point_on = bool(_get_dictlike(tbl, "point_on", False))
        point_number = _get_dictlike(tbl, "point_number", None)
        roll_index = _get_dictlike(tbl, "roll_index", None)

        # Persist to system for convenience
        self.system["comeout"] = comeout
        self.system["point_number"] = point_number if point_on else None

        # --- Player bankrolls / baselines (look in player subsection first)
        bankroll = _coerce_float(_get_dictlike(ply, "bankroll", None))
        starting = _coerce_float(_get_dictlike(ply, "starting", None))

        # Shooter / session flags may live at the GameState root
        is_new_shooter = bool(_get_dictlike(snapshot, "is_new_shooter", False))

        # Session baseline: prefer explicit "starting"; otherwise first bankroll seen.
        if "session_start_bankroll" not in self.system:
            if starting is not None:
                self.system["session_start_bankroll"] = starting
            elif bankroll is not None:
                self.system["session_start_bankroll"] = bankroll

        # Shooter baseline: reset on new shooter, otherwise set first time seen
        if is_new_shooter and bankroll is not None:
            self.system["shooter_start_bankroll"] = bankroll
        elif "shooter_start_bankroll" not in self.system and bankroll is not None:
            self.system["shooter_start_bankroll"] = bankroll

        # --- P&L (safe defaults to 0)
        ssb = _coerce_float(self.system.get("session_start_bankroll", bankroll))
        shb = _coerce_float(self.system.get("shooter_start_bankroll", bankroll))
        br = bankroll or 0.0
        self.system["pnl_session"] = (br - (ssb or 0.0))
        self.system["pnl_shooter"] = (br - (shb or 0.0))

        # --- Rolls since point
        if point_on:
            if isinstance(roll_index, int):
                # tests treat first roll under point as 0
                self.system["rolls_since_point"] = max(0, roll_index - 1)
            else:
                self.system["rolls_since_point"] = int(self.system.get("rolls_since_point", 0)) + 1
        else:
            self.system["rolls_since_point"] = 0

        # Keep last seen bankroll (optional)
        if bankroll is not None:
            self._last_bankroll = bankroll

    def apply_event_side_effects(self, event: Dict[str, Any], snapshot: Any) -> None:
        """
        Placeholder for optional event-driven counters.
        (No-Op for now to keep tests stable.)
        """
        return