# bet_ledger.py
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple
import time
import itertools
import copy


def _infer_category(bet: str) -> str:
    b = (bet or "").lower()
    if b in {"pass", "dont pass", "dp"}:
        return "line"
    if b in {"come", "dont come", "dc"}:
        return "come"
    if b.startswith("place") or b in {"4","5","6","8","9","10"}:
        return "place"
    if "hard" in b:
        return "hardway"
    if "field" in b:
        return "field"
    if "prop" in b or "yo" in b or "any" in b:
        return "prop"
    return "other"


@dataclass
class LedgerEntry:
    id: int
    created_ts: float
    bet: str
    amount: float
    category: str
    meta: Dict[str, Any] = field(default_factory=dict)
    # runtime
    status: str = "open"          # "open" | "closed"
    closed_ts: Optional[float] = None
    result: Optional[str] = None  # "win" | "lose" | "push" | None
    payout: float = 0.0           # amount returned incl. winnings (0 on a loss, amount on push)
    realized_pnl: float = 0.0     # payout - amount (push = 0)

    def snapshot(self) -> Dict[str, Any]:
        d = asdict(self)
        # shallow-copy meta to avoid downstream mutation
        d["meta"] = copy.deepcopy(d.get("meta", {}))
        return d


class BetLedger:
    """
    Standalone bet ledger:
      - Track open bets (exposure) and closed bets (realized P&L)
      - Attribute realized P&L to the current point cycle via `begin_point_cycle` / `end_point_cycle`
      - Provide a compact snapshot for UI/analytics
    """
    def __init__(self) -> None:
        self._entries: List[LedgerEntry] = []
        self._open_stack: Dict[str, List[int]] = {}  # key -> stack of open entry IDs (LIFO by bet key)
        self._id_seq = itertools.count(1)

        # Aggregates
        self._realized_pnl_total: float = 0.0
        self._open_exposure: float = 0.0

        # Since-point bookkeeping
        self._in_point_cycle: bool = False
        self._pnl_since_point: float = 0.0

        # Optional roll index linkage (not required by tests; set via touch_roll)
        self._current_roll_index: Optional[int] = None

    # ----- Point cycle hooks -------------------------------------------------

    def begin_point_cycle(self) -> None:
        self._in_point_cycle = True
        self._pnl_since_point = 0.0

    def end_point_cycle(self) -> None:
        self._in_point_cycle = False
        self._pnl_since_point = 0.0

    # ----- Roll attribution (optional) --------------------------------------

    def touch_roll(self, roll_index: int) -> None:
        """Link newly created/closed entries to a roll index (optional)."""
        self._current_roll_index = roll_index

    # ----- API: place & resolve ---------------------------------------------

    def place(self, bet: str, amount: float, *, category: Optional[str] = None, **meta: Any) -> int:
        if amount is None:
            raise ValueError("amount is required")
        if amount < 0:
            raise ValueError("amount must be >= 0")

        cat = category or _infer_category(bet)
        eid = next(self._id_seq)
        e = LedgerEntry(
            id=eid,
            created_ts=time.time(),
            bet=bet,
            amount=float(amount),
            category=cat,
            meta=dict(meta) if meta else {},
        )
        # Optional roll linkage
        if self._current_roll_index is not None:
            e.meta.setdefault("roll_index_opened", self._current_roll_index)

        self._entries.append(e)
        key = self._bet_key(bet, meta)
        self._open_stack.setdefault(key, []).append(eid)
        self._open_exposure += e.amount
        return eid

    def resolve(
        self,
        bet: str,
        *,
        result: str,           # "win" | "lose" | "push"
        payout: float = 0.0,   # full return incl. winnings; 0 on loss, amount on push
        entry_id: Optional[int] = None,
        apply_to_bankroll: bool = False,
        bankroll_hook: Optional[callable] = None,
        **meta: Any,
    ) -> Tuple[int, float]:
        """
        Close the most recent open entry for `bet` (LIFO) or a specific `entry_id`.
        Returns (entry_id, realized_pnl).
        If `apply_to_bankroll` and `bankroll_hook` are provided, calls bankroll_hook(pnl).
        """
        if entry_id is None:
            key = self._bet_key(bet, meta)
            if key not in self._open_stack or not self._open_stack[key]:
                raise KeyError(f"No open entry to resolve for bet={bet!r} meta={meta!r}")
            eid = self._open_stack[key].pop()
        else:
            eid = entry_id

        entry = self._by_id(eid)
        if entry.status != "open":
            raise ValueError(f"Entry {eid} already closed")

        entry.status = "closed"
        entry.closed_ts = time.time()
        entry.result = result
        entry.payout = float(payout)
        entry.realized_pnl = entry.payout - entry.amount

        # Optional roll linkage
        if self._current_roll_index is not None:
            entry.meta.setdefault("roll_index_closed", self._current_roll_index)

        # Aggregates
        self._open_exposure -= entry.amount
        self._realized_pnl_total += entry.realized_pnl
        if self._in_point_cycle:
            self._pnl_since_point += entry.realized_pnl

        # Optional bankroll application
        if apply_to_bankroll and bankroll_hook is not None and entry.realized_pnl != 0.0:
            bankroll_hook(entry.realized_pnl)

        return entry.id, entry.realized_pnl

    # ----- Snapshot ----------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        open_entries = [e.snapshot() for e in self._entries if e.status == "open"]
        closed_entries = [e.snapshot() for e in self._entries if e.status == "closed"]

        # Exposure by category
        exposure_by_cat: Dict[str, float] = {}
        for e in open_entries:
            exposure_by_cat[e["category"]] = exposure_by_cat.get(e["category"], 0.0) + float(e["amount"])

        # Realized P&L by category
        realized_by_cat: Dict[str, float] = {}
        for e in closed_entries:
            realized_by_cat[e["category"]] = realized_by_cat.get(e["category"], 0.0) + float(e["realized_pnl"])

        return {
            "open_count": len(open_entries),
            "closed_count": len(closed_entries),
            "open_exposure": round(self._open_exposure, 4),
            "realized_pnl": round(self._realized_pnl_total, 4),
            "realized_pnl_since_point": round(self._pnl_since_point, 4) if self._in_point_cycle else 0.0,
            "by_category": {
                "exposure": {k: round(v, 4) for k, v in exposure_by_cat.items()},
                "realized": {k: round(v, 4) for k, v in realized_by_cat.items()},
            },
            "open": open_entries,
            "closed": closed_entries[-50:],  # keep snapshot light
        }

    # ----- Utils -------------------------------------------------------------

    def _bet_key(self, bet: str, meta: Dict[str, Any]) -> str:
        """
        LIFO key: bet name + (sorted) discriminators if present (e.g., number)
        This keeps stacks separate for e.g. place-6 vs place-8.
        """
        parts = [str(bet).lower()]
        # common discriminators
        n = meta.get("number") or meta.get("point") or meta.get("box")
        if n is not None:
            parts.append(str(n))
        return "|".join(parts)

    def _by_id(self, eid: int) -> LedgerEntry:
        for e in self._entries:
            if e.id == eid:
                return e
        raise KeyError(f"Unknown entry id {eid}")