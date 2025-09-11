# crapssim_control/varstore.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Mapping


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if "." in key:
        h, t = key.split(".", 1)
        return _get(_get(obj, h), t, default)
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    if hasattr(obj, key):
        return getattr(obj, key)
    if hasattr(obj, "table") and key in ("comeout", "point_on", "point_number", "dice", "roll_index"):
        tbl = getattr(obj, "table")
        if tbl is not None and hasattr(tbl, key):
            return getattr(tbl, key)
    return default


def _dice_total(snapshot: Any) -> Optional[int]:
    dice = _get(snapshot, "table.dice")
    if isinstance(dice, (tuple, list)) and len(dice) >= 3:
        try:
            return int(dice[2])
        except Exception:
            pass
    return _get(snapshot, "total")


@dataclass
class VarStore:
    variables: Dict[str, Any] = field(default_factory=dict)
    system: Dict[str, Any] = field(default_factory=dict)
    counters: Dict[str, Any] = field(default_factory=dict)
    # ad-hoc user dict sometimes used by rules; keep present
    user: Dict[str, Any] = field(default_factory=dict)

    # internal memo
    _session_start: Optional[float] = None
    _shooter_start: Optional[float] = None
    _last_point_number: Optional[int] = None
    _last_roll_index: Optional[int] = None

    @classmethod
    def from_spec(cls, spec: Dict[str, Any]) -> "VarStore":
        vs = cls(variables=dict(spec.get("variables", {})))
        # Let tests inject table/bubble later; we keep system dict available.
        vs.system.setdefault("rolls_since_point", 0)
        return vs

    # -------- system refresh from a snapshot --------

    def refresh_system(self, snapshot: Any) -> None:
        """
        Update system vars from a snapshot (GameState or dict).
        Guarantees:
          - keys exist: rolls_since_point, pnl_session, pnl_shooter
          - rolls_since_point increments only on non-7 rolls while a point is on & unchanged
        """
        # basic keys
        comeout = bool(_get(snapshot, "table.comeout", _get(snapshot, "comeout", False)))
        point_on = bool(_get(snapshot, "table.point_on", _get(snapshot, "point_on", False)))
        point_number = _get(snapshot, "table.point_number", _get(snapshot, "point_number"))
        try:
            point_number = int(point_number) if point_number is not None else None
        except Exception:
            point_number = None

        roll_index = _get(snapshot, "table.roll_index", _get(snapshot, "roll_index"))
        try:
            roll_index = int(roll_index) if roll_index is not None else None
        except Exception:
            roll_index = None

        total = _dice_total(snapshot)

        # ensure keys
        self.system.setdefault("rolls_since_point", 0)
        self.system.setdefault("pnl_session", 0.0)
        self.system.setdefault("pnl_shooter", 0.0)

        # bankroll handling
        bankroll = _get(snapshot, "player.bankroll", _get(snapshot, "bankroll"))
        starting = _get(snapshot, "player.starting_bankroll", _get(snapshot, "starting"))
        is_new_shooter = bool(_get(snapshot, "is_new_shooter", False))

        # session PnL
        if self._session_start is None:
            base = starting if starting is not None else bankroll
            if base is not None:
                self._session_start = float(base)
        if bankroll is not None and self._session_start is not None:
            self.system["pnl_session"] = float(bankroll) - float(self._session_start)

        # shooter PnL
        if is_new_shooter or self._shooter_start is None:
            base = starting if starting is not None else bankroll
            if base is not None:
                self._shooter_start = float(base)
                self.system["pnl_shooter"] = 0.0
        elif bankroll is not None and self._shooter_start is not None:
            self.system["pnl_shooter"] = float(bankroll) - float(self._shooter_start)

        # rolls_since_point
        if not point_on or point_number is None:
            # point is off → reset
            self.system["rolls_since_point"] = 0
        else:
            if self._last_point_number != point_number:
                # new point established → reset to 0
                self.system["rolls_since_point"] = 0
            else:
                # same point; increment only when roll_index advances and total != 7
                if roll_index is not None and self._last_roll_index is not None:
                    if roll_index > self._last_roll_index and total != 7:
                        self.system["rolls_since_point"] += 1

        # update memo
        self._last_point_number = point_number
        if roll_index is not None:
            self._last_roll_index = roll_index