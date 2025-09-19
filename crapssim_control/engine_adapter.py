from __future__ import annotations
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .events import derive_event
try:
    from .adapters.vanilla_bridge import VanillaDriver  # optional
except Exception:  # pragma: no cover
    VanillaDriver = None  # type: ignore

def _bet_sig(bet: Any) -> Tuple:
    def g(obj, name, default=None):
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)
    return (
        g(bet, "kind"),
        round(float(g(bet, "amount", 0.0)), 4),
        g(bet, "point_number", None),
        round(float(g(bet, "odds", 0.0)), 4),
    )

def _list_bet_sigs(bets: Iterable[Any]) -> List[Tuple]:
    return sorted(_bet_sig(b) for b in list(bets or []))

class EngineAdapter:
    """
    Light adapter that drives a craps-like table one roll at a time.
    If the table lacks a single-roll method (vanilla crapssim), we fall back
    to a thin bridge that advances one roll via TableUpdate and exposes a view.
    """
    def __init__(self, table: Any, player: Any, strategy: Any):
        self.table = table
        self.player = player
        self.strategy = strategy
        self._vanilla_driver: Optional[Any] = None

    def play(self, *, shooters: int = 1, max_rolls_per_shooter: int = 200) -> None:
        shooters_remaining = shooters
        while shooters_remaining > 0:
            for _ in range(max_rolls_per_shooter):
                event = self._roll_once()
                if (event or {}).get("event") in ("seven_out", "shooter_change"):
                    break
            shooters_remaining -= 1

    def _ensure_vanilla_driver(self):
        if self._vanilla_driver is not None or VanillaDriver is None:
            return
        # Heuristic: vanilla has .dice/.point but no 'roll_once'/'roll'/'step'
        if hasattr(self.table, "dice") and hasattr(self.table, "point") and not any(
            hasattr(self.table, name) for name in ("roll_once", "roll", "step")
        ):
            self._vanilla_driver = VanillaDriver(self.table, self.strategy)

    def _roll_once(self) -> Optional[Dict[str, Any]]:
        prev_snapshot = self._snapshot_for_events(self.table)

        # Pre-roll strategy hook (skip if vanilla bridge will call it for us)
        self._ensure_vanilla_driver()
        if self._vanilla_driver is None:
            try:
                self.strategy.update_bets(self.table)
            except TypeError:
                self.strategy.update_bets(self.table)

        # Advance one roll
        if hasattr(self.table, "roll_once"):
            self.table.roll_once()
        elif hasattr(self.table, "roll"):
            self.table.roll()
        else:
            step = getattr(self.table, "step", None)
            if callable(step):
                step()
            else:
                self._ensure_vanilla_driver()
                if self._vanilla_driver is not None:
                    self._vanilla_driver.roll_once()
                else:
                    raise RuntimeError("EngineAdapter: cannot find a roll method on the table")

        curr_snapshot = self._snapshot_for_events(self.table)

        event = derive_event(prev_snapshot, curr_snapshot) or {"event": "roll"}

        try:
            self.strategy.after_roll(self.table, event)
        except TypeError:
            try:
                self.strategy.after_roll(self.table, event)
            except Exception:
                pass

        return event

    def _get_player_bets(self) -> List[Any]:
        player = self._first_player()
        if player is None:
            return []
        bets = getattr(player, "bets", None)
        if bets is None and isinstance(player, dict):
            bets = player.get("bets")
        return list(bets or [])

    def _first_player(self):
        players = getattr(self.table, "players", None)
        if players is None and isinstance(self.table, dict):
            players = self.table.get("players")
        if players and len(players) > 0:
            return players[0]
        single = getattr(self.table, "player", None)
        if single is None and isinstance(self.table, dict):
            single = self.table.get("player")
        return single or self.player

    def _snapshot_for_events(self, table: Any) -> Dict[str, Any]:
        def g(obj, name, default=None):
            if isinstance(obj, dict):
                return obj.get(name, default)
            return getattr(obj, name, default)

        # Prefer a .view (vanilla bridge) but fall back to table itself
        view = getattr(table, "view", table)

        point_number = g(view, "point_number", None)
        comeout = bool(g(view, "comeout", False))
        total = g(view, "total", None)
        roll_index = g(view, "roll_index", None)
        just_est = g(view, "just_established_point", False)
        just_made = g(view, "just_made_point", False)

        # vanilla fallbacks
        if point_number is None and hasattr(table, "point"):
            point_number = getattr(getattr(table, "point", None), "number", None)
            comeout = bool(point_number is None)
        if total is None and hasattr(table, "dice"):
            total = int(getattr(getattr(table, "dice", None), "total", 0))
        if roll_index is None and hasattr(table, "dice"):
            roll_index = int(getattr(getattr(table, "dice", None), "n_rolls", 0))

        return {
            "comeout": comeout,
            "point_on": bool(point_number is not None),
            "point_num": point_number,
            "just_est": bool(just_est),
            "just_made": bool(just_made),
            "total": int(total or 0),
            "roll_index": roll_index,
        }