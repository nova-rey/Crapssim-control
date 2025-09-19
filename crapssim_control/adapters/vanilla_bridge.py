# crapssim_control/adapters/vanilla_bridge.py
from __future__ import annotations
from typing import Any, Dict, Optional

try:
    # Vanilla crapssim
    from crapssim.table import Table, TableUpdate, Player  # type: ignore
except Exception as e:  # pragma: no cover
    Table = object  # type: ignore
    TableUpdate = None  # type: ignore
    Player = object  # type: ignore

class _ProxyStrategy:
    """
    Tiny shim that looks like a vanilla Strategy but delegates to a
    crapssim_control-style controller (ctrl).
    """
    def __init__(self, ctrl: Any):
        self.ctrl = ctrl
        # track previous point_on to detect seven_out
        self._prev_point_on: Optional[bool] = None

    def update_bets(self, player: Any) -> None:
        # vanilla calls this with the Player; forward table to ctrl
        table = getattr(player, "table", None)
        if table is None:
            return
        try:
            self.ctrl.update_bets(table)  # type: ignore[attr-defined]
        except TypeError:
            self.ctrl.update_bets(table)  # best effort

    def after_roll(self, player: Any) -> None:
        table = getattr(player, "table", None)
        if table is None:
            return
        point_on = bool(getattr(table.point, "status", "Off") == "On")
        total = int(getattr(table.dice, "total", 0))
        ev = None
        if (self._prev_point_on is True) and total == 7:
            ev = {"event": "seven_out"}
        self._prev_point_on = point_on
        try:
            if ev:
                self.ctrl.after_roll(table, ev)  # type: ignore[attr-defined]
            else:
                self.ctrl.after_roll(table, {"event": "roll"})
        except TypeError:
            pass

class VanillaDriver:
    """
    Per-roll driver over vanilla crapssim.Table using TableUpdate.
    Exposes .view resembling the loose shape expected by CSC engine_adapter.
    """
    def __init__(self, table: Any, ctrl: Any):
        if TableUpdate is None:
            raise RuntimeError("crapssim is not available")
        self.table: Table = table
        proxy = _ProxyStrategy(ctrl)
        # Add a real Player so vanilla will invoke our proxy
        self._player = self.table.add_player(bankroll=1000, strategy=proxy, name="CSC-Proxy")  # type: ignore[attr-defined]
        self._just_established_point = False
        self._just_made_point = False
        self._last_point_number: Optional[int] = getattr(self.table.point, "number", None)

    def roll_once(self) -> None:
        before_point = getattr(self.table.point, "number", None)
        TableUpdate().run(self.table, run_complete=False, verbose=False)  # type: ignore
        after_point = getattr(self.table.point, "number", None)
        self._just_established_point = (before_point is None and after_point is not None)
        self._just_made_point = (before_point is not None and after_point is None)
        self._last_point_number = after_point

    @property
    def view(self) -> Dict[str, Any]:
        point_num = getattr(self.table.point, "number", None)
        comeout = bool(point_num is None)
        return {
            "comeout": comeout,
            "point_number": point_num,
            "just_established_point": bool(self._just_established_point),
            "just_made_point": bool(self._just_made_point),
            "roll_index": int(getattr(self.table.dice, "n_rolls", 0)),
            "total": int(getattr(self.table.dice, "total", 0)),
        }