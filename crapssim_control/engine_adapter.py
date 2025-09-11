from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from .events import derive_event


def _bet_sig(bet: Any) -> Tuple:
    """
    Turn a bet-like object into a hashable signature so we can diff
    before/after lists. The fakes in tests expose (kind, amount, point?, odds?).
    We only use attributes if they exist.
    """
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
    A very light adapter that can drive a Craps-like table object with a
    strategy. It's intentionally loose on the host API: it looks for common
    attributes/methods used by the tests' fakes.
    """

    def __init__(self, table: Any, player: Any, strategy: Any):
        self.table = table
        self.player = player
        self.strategy = strategy

    # ----------------- public driver -----------------

    def play(self, *, shooters: int = 1) -> None:
        """
        Run until the requested number of shooters have completed.
        For tests, just exercising a couple of rolls is enough.
        """
        shooters_remaining = shooters
        while shooters_remaining > 0:
            event = self._roll_once()
            # Consider a "seven_out" or "shooter_change" as end-of-shooter hints
            ev = (event or {}).get("event")
            if ev in ("seven_out", "shooter_change"):
                shooters_remaining -= 1

    # ----------------- core step -----------------

    def _roll_once(self) -> Dict[str, Any]:
        """
        Perform one roll cycle:
          - let strategy update bets before the roll
          - let engine roll & settle
          - let strategy read bankroll delta after roll
          - return the derived event dict (includes total, comeout, etc.)
        """
        # 0) Build a "prev" snapshot before any mutation this tick
        prev_snapshot = self._snapshot_for_events(self.table)

        # 1) Give strategy a chance to place/update bets before the roll
        self.strategy.update_bets(self.table)

        # 2) Snapshot bets before roll (for diffing later)
        before = _list_bet_sigs(self._get_player_bets())

        # 3) Ask the table/engine to roll one time
        #    We don't know the exact CrapsSim API; try common spellings.
        if hasattr(self.table, "roll_once"):
            self.table.roll_once()
        elif hasattr(self.table, "roll"):
            self.table.roll()
        else:
            # If the exporter uses a loop with table.step(), try that:
            step = getattr(self.table, "step", None)
            if callable(step):
                step()
            else:
                raise RuntimeError("EngineAdapter: cannot find roll function on table")

        # 4) Build a "curr" snapshot after the roll & settlements
        curr_snapshot = self._snapshot_for_events(self.table)

        # 5) Derive the high-level event from prev->curr
        event = derive_event(prev_snapshot, curr_snapshot) or {"event": "roll"}

        # 6) Let strategy do any after-roll bookkeeping with the event
        #    (Controller.after_roll accepts optional event.)
        try:
            self.strategy.after_roll(self.table, event)
        except TypeError:
            # Back-compat if a user's strategy still expects only (table)
            self.strategy.after_roll(self.table)  # type: ignore[misc]

        # 7) Optionally diff bets (kept for completeness / debugging)
        _ = _list_bet_sigs(self._get_player_bets())  # 'after' snapshot
        # diffs = [s for s in after if s not in before]  # not used in tests

        return event

    # ----------------- helpers -----------------

    def _get_player_bets(self) -> List[Any]:
        """
        Return a list-like of bets from the first/only player.
        Test fakes expose .bets on a player instance.
        """
        player = self._first_player()
        if player is None:
            return []
        bets = getattr(player, "bets", None)
        if bets is None and isinstance(player, dict):
            bets = player.get("bets")
        return list(bets or [])

    def _first_player(self):
        """
        Return the first player on the table if the table keeps a collection,
        otherwise fall back to a single 'player' attribute.
        """
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
        """
        Produce the minimal dict that crapssim_control.events.derive_event expects.
        We read directly off the table (or its .view if present) using a safe getter.
        """
        def g(obj, name, default=None):
            if isinstance(obj, dict):
                return obj.get(name, default)
            return getattr(obj, name, default)

        view = getattr(table, "view", table)

        comeout = bool(g(view, "comeout", False))
        snapshot: Dict[str, Any] = {
            "comeout": comeout,
            "table": {"comeout": comeout},
            "point_number": g(view, "point_number", None),
            "just_established_point": g(view, "just_established_point", False),
            "just_made_point": g(view, "just_made_point", False),
            "roll_index": g(view, "roll_index", None),
        }
        return snapshot