# tracker_ledger_shim.py
from __future__ import annotations
from typing import Any, Dict, Optional
from bet_ledger import BetLedger


def wire_ledger(tracker_obj: Any) -> None:
    """
    Mutates a live Tracker instance to add:
      - tracker_obj.ledger : BetLedger
      - tracker_obj.on_bet_placed(event: dict)
      - tracker_obj.on_bet_resolved(event: dict)
      - tracker_obj.on_intent_created(event: dict)   # NEW in Batch 6
      - tracker_obj.on_intent_canceled(intent_id, reason=None)  # NEW
      - snapshot() now includes "ledger" section (non-breaking)
      - point-cycle hooks bridged to ledger
    """
    if hasattr(tracker_obj, "ledger") and isinstance(tracker_obj.ledger, BetLedger):
        # Already wired
        pass
    else:
        tracker_obj.ledger = BetLedger()

    # ----- Bridge point-cycle + roll ----------------------------------------

    prev_begin_point = getattr(tracker_obj, "on_point_established", None)
    prev_point_made = getattr(tracker_obj, "on_point_made", None)
    prev_roll_hook = getattr(tracker_obj, "on_roll", None)

    def on_point_established_wrapper(*args, **kwargs):
        try:
            tracker_obj.ledger.begin_point_cycle()
        except Exception:
            pass
        if callable(prev_begin_point):
            return prev_begin_point(*args, **kwargs)

    def on_point_made_wrapper(*args, **kwargs):
        try:
            tracker_obj.ledger.end_point_cycle()
        except Exception:
            pass
        if callable(prev_point_made):
            return prev_point_made(*args, **kwargs)

    def on_roll_wrapper(*args, **kwargs):
        # assume tracker has roll counter; otherwise ignore
        try:
            roll_index = getattr(tracker_obj, "roll").shooter_rolls  # best effort
            tracker_obj.ledger.touch_roll(int(roll_index))
        except Exception:
            pass
        if callable(prev_roll_hook):
            return prev_roll_hook(*args, **kwargs)

    if callable(prev_begin_point):
        setattr(tracker_obj, "on_point_established", on_point_established_wrapper)
    if callable(prev_point_made):
        setattr(tracker_obj, "on_point_made", on_point_made_wrapper)
    if callable(prev_roll_hook):
        setattr(tracker_obj, "on_roll", on_roll_wrapper)

    # ----- Bet hooks ---------------------------------------------------------

    def on_bet_placed(event: Dict[str, Any]) -> None:
        """
        Expected event keys (best-effort):
          - bet: str
          - amount: float
          - number/point/box: Optional[int]
          - intent_id: Optional[int]
        """
        bet = str(event.get("bet", ""))
        amount = float(event.get("amount", 0.0))
        meta = dict(event)
        meta.pop("bet", None)
        meta.pop("amount", None)
        try:
            tracker_obj.ledger.place(bet, amount, **meta)
        except Exception:
            # Never crash caller
            pass

    def on_bet_resolved(event: Dict[str, Any]) -> None:
        """
        Expected event keys:
          - bet: str
          - result: 'win'|'lose'|'push'
          - payout: float (full return incl winnings; 0 on loss, amount on push)
          - entry_id (optional): prefer exact resolution by id
        """
        bet = str(event.get("bet", ""))
        result = str(event.get("result", "")) or str(event.get("outcome", ""))
        payout = float(event.get("payout", 0.0))
        entry_id = event.get("entry_id")
        meta = dict(event)
        for k in ("bet", "result", "outcome", "payout", "entry_id"):
            meta.pop(k, None)
        try:
            tracker_obj.ledger.resolve(bet, result=result, payout=payout, entry_id=entry_id, **meta)
        except Exception:
            pass

    setattr(tracker_obj, "on_bet_placed", on_bet_placed)
    setattr(tracker_obj, "on_bet_resolved", on_bet_resolved)

    # ----- Intent hooks (Batch 6) -------------------------------------------

    def on_intent_created(event: Dict[str, Any]) -> Optional[int]:
        """
        Expected event keys (suggested):
          - bet: str
          - stake: Optional[float]
          - number/point/box: Optional[int]
          - reason: Optional[str] (why plan was formed, e.g. 'hedge', 'odds_entry')
          - any extra tags/metadata
        Returns the intent_id for convenience.
        """
        bet = str(event.get("bet", ""))
        stake = event.get("stake")
        number = event.get("number") or event.get("point") or event.get("box")
        reason = event.get("reason")
        meta = dict(event)
        for k in ("bet", "stake", "number", "point", "box", "reason"):
            meta.pop(k, None)
        try:
            iid = tracker_obj.ledger.create_intent(bet=bet, stake=stake, number=number, reason=reason, **meta)
            return iid
        except Exception:
            return None

    def on_intent_canceled(intent_id: int, reason: Optional[str] = None) -> None:
        try:
            tracker_obj.ledger.cancel_intent(int(intent_id), reason=reason)
        except Exception:
            pass

    setattr(tracker_obj, "on_intent_created", on_intent_created)
    setattr(tracker_obj, "on_intent_canceled", on_intent_canceled)

    # ----- Snapshot wrapper --------------------------------------------------

    prev_snapshot = getattr(tracker_obj, "snapshot")

    def snapshot_with_ledger(*args, **kwargs):
        snap = prev_snapshot(*args, **kwargs)
        try:
            snap["ledger"] = tracker_obj.ledger.snapshot()
        except Exception:
            # Never let ledger break an existing snapshot
            snap["ledger"] = {
                "open_count": 0,
                "closed_count": 0,
                "open_exposure": 0.0,
                "realized_pnl": 0.0,
                "realized_pnl_since_point": 0.0,
                "by_category": {"exposure": {}, "realized": {}},
                "open": [],
                "closed": [],
                "intents": {
                    "open_count": 0, "matched_count": 0, "canceled_count": 0,
                    "open": [], "matched": [], "canceled": []
                },
            }
        return snap

    setattr(tracker_obj, "snapshot", snapshot_with_ledger)