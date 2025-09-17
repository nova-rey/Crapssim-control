# bet_ledger.py -- Batch 6 + Batch 9 (canon type tagging)
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple
import time
import itertools
import copy

from .bet_types import normalize_bet_type  # NEW


# --------------------------
# Helpers / categorization
# --------------------------

def _infer_category(bet: str) -> str:
    b = (bet or "").lower()
    if b in {"pass", "pass line", "pass_line", "dont pass", "don't pass", "dp"}:
        return "line"
    if b in {"come", "dont come", "don't come", "dc"}:
        return "come"
    if b.startswith("place") or b in {"4","5","6","8","9","10"}:
        return "place"
    if "odds" in b:
        return "odds"
    if "field" in b:
        return "field"
    if "hard" in b:
        return "hardways"
    if "lay" in b:
        return "lay"
    return "other"


def _lifo_key(bet: str, meta: Dict[str, Any]) -> str:
    """
    LIFO key: bet name + (sorted) discriminators if present (e.g., number)
    Keeps stacks separate (e.g., place-6 vs place-8).
    """
    parts = [str(bet).lower()]
    n = meta.get("number") or meta.get("point") or meta.get("box")
    if n is not None:
        parts.append(str(n))
    return "|".join(parts)


# --------------------------
# Core Entries
# --------------------------

@dataclass
class LedgerEntry:
    id: int
    created_ts: float
    bet: str
    amount: float
    category: str
    status: str = "open"           # "open" | "closed"
    payout: float = 0.0
    result: Optional[str] = None   # "win" | "lose" | "push" | None
    realized_pnl: float = 0.0
    meta: Dict[str, Any] = field(default_factory=dict)
    closed_ts: Optional[float] = None

    def snapshot(self) -> Dict[str, Any]:
        d = asdict(self)
        d["meta"] = copy.deepcopy(d.get("meta", {}))
        return d


# --------------------------
# Intent entries (Batch 6)
# --------------------------

@dataclass
class IntentEntry:
    id: int
    created_ts: float
    bet: str
    stake: Optional[float] = None
    number: Optional[int] = None
    status: str = "open"              # "open" | "matched" | "canceled"
    reason: Optional[str] = None      # reason code for cancel
    matched_entry_id: Optional[int] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    created_roll_index: Optional[int] = None
    canceled_ts: Optional[float] = None
    matched_ts: Optional[float] = None

    def snapshot(self) -> Dict[str, Any]:
        d = asdict(self)
        d["meta"] = copy.deepcopy(d.get("meta", {}))
        return d


# --------------------------
# BetLedger
# --------------------------

class BetLedger:
    """
    Standalone bet ledger:
      - Track open bets (exposure) and closed bets (realized P&L)
      - Attribute realized P&L to the current point cycle via `begin_point_cycle` / `end_point_cycle`
      - Track strategy intents and match them to actual bets (Batch 6)
      - Tag entries with canonical bet type (Batch 9) for clean exports
      - Provide a compact snapshot for UI/analytics
    """
    def __init__(self) -> None:
        # bets
        self._entries: List[LedgerEntry] = []
        self._open_stack: Dict[str, List[int]] = {}
        self._id_seq = itertools.count(1)
        self._realized_pnl_total: float = 0.0
        self._open_exposure: float = 0.0

        # point-cycle accounting
        self._in_point_cycle: bool = False
        self._pnl_since_point: float = 0.0

        # roll index (optional)
        self._current_roll_index: Optional[int] = None

        # intents (Batch 6)
        self._intents: List[IntentEntry] = []
        self._intent_id_seq = itertools.count(1)

    # ----- Bets API ----------------------------------------------------------

    def place(self, bet: str, amount: float, *, category: Optional[str] = None, **meta: Any) -> int:
        if amount is None:
            raise ValueError("amount is required")
        if amount < 0:
            raise ValueError("amount must be >= 0")

        # Compute canon bet type for analytics
        canon_type = normalize_bet_type(bet, meta)
        cat = category or _infer_category(canon_type or bet)

        # include canon+raw in meta (don't overwrite user fields)
        meta = dict(meta) if meta else {}
        meta.setdefault("raw_bet_type", bet)
        meta.setdefault("canon_bet_type", canon_type)

        eid = next(self._id_seq)
        e = LedgerEntry(
            id=eid,
            created_ts=time.time(),
            bet=canon_type or (bet or ""),
            amount=float(amount),
            category=cat,
            meta=meta,
        )

        # Optional roll linkage
        if self._current_roll_index is not None:
            e.meta.setdefault("roll_index_opened", self._current_roll_index)

        # Intent linking (Batch 6)
        intent_id = e.meta.get("intent_id")
        if intent_id is not None:
            self._mark_intent_matched(int(intent_id), eid)
        else:
            self._maybe_match_nearest_intent(eid, bet, e.meta)

        self._entries.append(e)
        key = _lifo_key(e.bet, e.meta)
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
        """
        # Use canon key in search to avoid mismatches
        canon = normalize_bet_type(bet, meta)
        key_meta = dict(meta or {})
        key = _lifo_key(canon or bet, key_meta)

        # Find entry
        if entry_id is None:
            stack = self._open_stack.get(key) or []
            if not stack:
                # fallback: try raw bet key if canon didn't match (back-compat)
                key_fallback = _lifo_key(bet, key_meta)
                stack = self._open_stack.get(key_fallback) or []
                if not stack:
                    raise KeyError(f"No open {bet} to resolve for key={key}")
            entry_id = stack.pop()
        entry = self._by_id(entry_id)

        if entry.status != "open":
            raise ValueError(f"Entry {entry_id} is already {entry.status}")

        # Update entry
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

        # Bankroll hook
        if apply_to_bankroll and bankroll_hook is not None:
            try:
                bankroll_hook(entry.realized_pnl)
            except Exception:
                pass

        return entry_id, entry.realized_pnl

    # ----- Point cycle hooks -------------------------------------------------

    def begin_point_cycle(self) -> None:
        self._in_point_cycle = True
        self._pnl_since_point = 0.0

    def end_point_cycle(self) -> None:
        self._in_point_cycle = False
        self._pnl_since_point = 0.0

    # ----- Roll attribution (optional) --------------------------------------

    def touch_roll(self, roll_index: int) -> None:
        """Optionally attribute opening/closing to a roll index for debugging."""
        self._current_roll_index = int(roll_index)

    # ----- Intents API (Batch 6) --------------------------------------------

    def create_intent(self, *, bet: str, stake: Optional[float] = None, number: Optional[int] = None,
                      reason: Optional[str] = None, **meta: Any) -> int:
        iid = next(self._intent_id_seq)
        ie = IntentEntry(
            id=iid,
            created_ts=time.time(),
            bet=normalize_bet_type(bet, meta) or bet,
            stake=stake,
            number=int(number) if number is not None else None,
            status="open",
            reason=reason,
            meta=dict(meta) if meta else {},
            created_roll_index=self._current_roll_index,
        )
        # keep raw as well for audit
        ie.meta.setdefault("raw_bet_type", bet)
        ie.meta.setdefault("canon_bet_type", ie.bet)
        self._intents.append(ie)
        return iid

    def cancel_intent(self, intent_id: int, *, reason: Optional[str] = None) -> None:
        ie = self._intent_by_id(intent_id)
        if ie.status != "open":
            return
        ie.status = "canceled"
        ie.reason = reason or ie.reason or "canceled"
        ie.canceled_ts = time.time()

    def _intent_by_id(self, iid: int) -> IntentEntry:
        for ie in self._intents:
            if ie.id == iid:
                return ie
        raise KeyError(f"Unknown intent id {iid}")

    def _mark_intent_matched(self, intent_id: int, entry_id: int) -> None:
        try:
            ie = self._intent_by_id(intent_id)
        except KeyError:
            return
        if ie.status != "open":
            return
        ie.status = "matched"
        ie.matched_entry_id = entry_id
        ie.matched_ts = time.time()

    def _maybe_match_nearest_intent(self, entry_id: int, bet: str, meta: Dict[str, Any]) -> None:
        """Best-effort implicit matching: same canon bet & (optional) number, most recent open intent."""
        canon = normalize_bet_type(bet, meta)
        number = meta.get("number") or meta.get("point") or meta.get("box")
        candidate: Optional[IntentEntry] = None
        for ie in reversed(self._intents):
            if ie.status != "open":
                continue
            if (ie.bet or "").lower() != (canon or bet or "").lower():
                continue
            if number is not None and ie.number is not None and int(ie.number) != int(number):
                continue
            candidate = ie
            break
        if candidate is not None:
            self._mark_intent_matched(candidate.id, entry_id)

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

        # Intent summary
        intents_open = [i.snapshot() for i in self._intents if i.status == "open"]
        intents_matched = [i.snapshot() for i in self._intents if i.status == "matched"]
        intents_canceled = [i.snapshot() for i in self._intents if i.status == "canceled"]

        return {
            "open_count": len(open_entries),
            "closed_count": len(closed_entries),
            "open_exposure": float(self._open_exposure),
            "realized_pnl": float(self._realized_pnl_total),
            "realized_pnl_since_point": float(self._pnl_since_point),
            "by_category": {
                "exposure": exposure_by_cat,
                "realized": realized_by_cat,
            },
            "open": open_entries,
            "closed": closed_entries[-50:],  # keep snapshot light
            "intents": {
                "open_count": len(intents_open),
                "matched_count": len(intents_matched),
                "canceled_count": len(intents_canceled),
                "open": intents_open[-50:],
                "matched": intents_matched[-50:],
                "canceled": intents_canceled[-50:],
            },
        }

    # ----- Utils -------------------------------------------------------------

    def _by_id(self, eid: int) -> LedgerEntry:
        for e in self._entries:
            if e.id == eid:
                return e
        raise KeyError(f"Unknown entry id {eid}")