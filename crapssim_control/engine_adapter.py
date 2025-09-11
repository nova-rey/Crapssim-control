# crapssim_control/engine_adapter.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .events import derive_event

# ---------- Helpers to read bets defensively ----------

def _bet_signature(b: Any) -> Tuple[str, Optional[int], float, float]:
    """Summarize a bet as (family, number, flat_amt, odds_amt) using best-effort introspection."""
    # family
    fam = getattr(b, "kind", None) or getattr(b, "family", None) or b.__class__.__name__.lower()
    # normalize some common names
    fam_map = {
        "betpassline": "pass",
        "betdontpass": "dont_pass",
        "betcome": "come",
        "betdontcome": "dont_come",
        "betfield": "field",
    }
    fam = fam_map.get(fam, fam)

    # number (e.g., 4/5/6/8/9/10) if present
    num = getattr(b, "number", None)
    if isinstance(num, bool):  # just in case
        num = None

    # flat amount
    flat = float(getattr(b, "amount", 0.0) or 0.0)

    # odds amount (come/DP/lay variants differ)
    # common attributes we’ve seen: odds_amount, lay_odds
    odds = float(
        getattr(b, "odds_amount", None)
        if getattr(b, "odds_amount", None) is not None
        else (getattr(b, "lay_odds", 0.0) or 0.0)
    )

    return (str(fam), int(num) if (num is not None) else None, flat, odds)


def _list_bet_sigs(bets: List[Any]) -> Dict[Tuple[str, Optional[int]], Tuple[float, float]]:
    """Map (family, number) -> (flat, odds) for snapshot diffing."""
    out: Dict[Tuple[str, Optional[int]], Tuple[float, float]] = {}
    for b in bets or []:
        fam, num, flat, odds = _bet_signature(b)
        out[(fam, num)] = (flat, odds)
    return out


# ---------- Very small rules to classify trivial resolutions ----------

def _classify_unambiguous(
    family: str,
    number: Optional[int],
    total: int,
    point: int,
    comeout: bool,
) -> Optional[str]:
    """
    Return 'win' | 'lose' | 'push' when obvious from dice/point alone.
    Keep this intentionally small/safe to avoid wrong calls.
    """
    f = family
    n = number

    if f == "field":
        # Common field: wins on 2,3,4,9,10,11; loses on 5,6,7,8; pushes rarely (house variants)
        return "win" if total in (2, 3, 4, 9, 10, 11) else ("lose" if total in (5, 6, 7, 8) else None)

    if f == "any_seven":
        return "win" if total == 7 else "lose"

    if f == "any_craps":
        return "win" if total in (2, 3, 12) else "lose"

    if f == "pass":
        if comeout:
            if total in (7, 11): return "win"
            if total in (2, 3, 12): return "lose"
        else:
            if total == point: return "win"
            if total == 7: return "lose"
        return None

    if f == "dont_pass":
        if comeout:
            if total in (2, 3): return "win"
            if total in (7, 11): return "lose"
            if total == 12: return "push"  # bar 12, typical
        else:
            if total == 7: return "win"
            if total == point: return "lose"
        return None

    # For come/don’t come & numbered bets we usually need state transitions,
    # so we don’t guess here in Phase 1.
    return None


# ---------- Engine runner / adapter ----------

@dataclass
class EngineAdapter:
    """
    Wraps a CrapsSim table & player and feeds ControlStrategy hooks without modifying the engine.

    Usage (conceptual):
        table = Table(...)
        player = YourExporterPlayer(...)
        strategy = ControlStrategy(spec, telemetry=..., odds_policy="3-4-5x")
        adapter = EngineAdapter(table, player, strategy)
        adapter.play(shooters=100)
    """
    table: Any
    player: Any
    strategy: Any  # ControlStrategy

    def _get_player_bets(self) -> List[Any]:
        # Prefer the real player’s bet list if available
        if hasattr(self.player, "bets"):
            return list(getattr(self.player, "bets") or [])
        # Some engines keep bets on table.current_player
        cp = getattr(self.table, "current_player", None)
        if cp is not None and hasattr(cp, "bets"):
            return list(getattr(cp, "bets") or [])
        return []

    def _comeout_flag(self) -> bool:
        # If engine exposes a flag, use it; else infer from point
        if hasattr(self.table, "comeout"):
            return bool(getattr(self.table, "comeout"))
        # infer by point
        pt = getattr(self.table, "point", 0) or 0
        return pt in (0, None)

    def _point_value(self) -> int:
        return int(getattr(self.table, "point", 0) or 0)

    def _roll_once(self) -> Dict[str, Any]:
        """
        Perform one roll cycle:
          - let strategy update bets before the roll
          - let engine roll & settle
          - let strategy read bankroll delta after roll
          - return the derived event dict (includes total, comeout, etc.)
        """
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

        # 4) Let strategy consume roll/bankroll info
        self.strategy.after_roll(self.table)

        # 5) Derive event (has total, comeout, seven_out, point_established, etc.)
        event = derive_event(self.table) or {"event": "roll"}
        return event

    def _emit_unambiguous_resolutions(self, event: Dict[str, Any]) -> None:
        """For simple families (field/any7/anycraps/pass/dp), emit on_bet_resolved without diffing."""
        total = int(event.get("total", 0) or 0)
        point = int(getattr(self.table, "point", 0) or 0)
        comeout = bool(event.get("comeout", self._comeout_flag()))

        # look through active bets and classify only the easy ones
        for b in self._get_player_bets():
            fam, num, flat, odds = _bet_signature(b)
            res = _classify_unambiguous(fam, num, total, point, comeout)
            if res is None:
                continue
            # We don’t know exact deltas per bet without engine internals; send 0 deltas (the PnL is still captured by after_roll()).
            self.strategy.on_bet_resolved(
                bet_kind=fam, result=res, number=num,
                flat_delta=0.0, odds_delta=0.0,
                stake_flat=flat, stake_odds=odds,
                extra={"source": "adapter_unambiguous"}
            )

    def _diff_and_emit(self, before: Dict[Tuple[str, Optional[int]], Tuple[float, float]], after: Dict[Tuple[str, Optional[int]], Tuple[float, float]], event: Dict[str, Any]) -> None:
        """
        Phase 2 (optional): If a bet disappeared or changed, infer resolution and emit.
        Currently conservative: marks disappearance as 'resolved' and leaves result unknown (skips).
        You can enhance this with per-family rules keyed by roll/point.
        """
        # Differences
        removed = set(before.keys()) - set(after.keys())
        # changed = {k for k in before.keys() & after.keys() if before[k] != after[k]}

        if not removed:
            return

        total = int(event.get("total", 0) or 0)
        point = int(getattr(self.table, "point", 0) or 0)
        comeout = bool(event.get("comeout", self._comeout_flag()))

        for k in removed:
            fam, num = k
            flat, odds = before[k]
            # Try to classify with our unambiguous helper; otherwise skip for now
            res = _classify_unambiguous(fam, num, total, point, comeout)
            if res is None:
                # TODO: extend family/number rules (come/DC moves, place/buy/lay by box number, hardways, etc.)
                continue
            self.strategy.on_bet_resolved(
                bet_kind=fam, result=res, number=num,
                flat_delta=0.0, odds_delta=0.0,
                stake_flat=flat, stake_odds=odds,
                extra={"source": "adapter_diff_removed"}
            )

    def play(self, shooters: int = 1) -> None:
        """
        Drive the table for N shooters. This assumes the underlying Table advances shooters on seven-out or point-resolved,
        which CrapsSim typically does. We rely on derive_event() to spot shooter changes.
        """
        shooters_done = 0

        while shooters_done < shooters:
            # snapshot before roll
            before = _list_bet_sigs(self._get_player_bets())

            event = self._roll_once()

            # classify easy ones (line/center)
            self._emit_unambiguous_resolutions(event)

            # phase-2 diff (conservative until we wire full rules)
            after = _list_bet_sigs(self._get_player_bets())
            self._diff_and_emit(before, after, event)

            # shooter advancement (from derived events)
            if event.get("event") in ("seven_out", "point_made", "shooter_change"):
                # count "completed hands" on seven_out or explicit shooter change
                if event.get("event") in ("seven_out", "shooter_change"):
                    shooters_done += 1