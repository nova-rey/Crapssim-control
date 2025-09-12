# tracker_ledger_shim.py
from __future__ import annotations
from typing import Any, Dict
from bet_ledger import BetLedger


def wire_ledger(tracker_obj: Any) -> None:
    """
    Mutates a live Tracker instance to add:
      - tracker_obj.ledger : BetLedger
      - tracker_obj.on_bet_placed(...)
      - tracker_obj.on_bet_resolved(...)
      - snapshot() now includes "ledger" section (non-breaking)
      - point-cycle hooks bridged to ledger
    """
    if hasattr(tracker_obj, "ledger") and isinstance(tracker_obj.ledger, BetLedger):
        return  # already wired

    ledger = BetLedger()
    tracker_obj.ledger = ledger

    # --- Bridge existing roll index (if tracker has one) into ledger (optional) ---
    if hasattr(tracker_obj, "_roll") and isinstance(getattr(tracker_obj, "_roll"), dict):
        # best effort: expose a method tracker_obj._touch_roll_index(i) that updates ledger too
        original_on_roll = getattr(tracker_obj, "on_roll", None)

        def on_roll_with_ledger(n: int) -> None:
            if original_on_roll:
                original_on_roll(n)
            # try to derive a roll index if tracker maintains one; else just increment locally
            idx = None
            if "shooter_rolls" in tracker_obj._roll:
                idx = tracker_obj._roll.get("shooter_rolls")
            ledger.touch_roll(idx if idx is not None else 0)

        setattr(tracker_obj, "on_roll", on_roll_with_ledger)

    # --- Bridge point cycle ---
    original_point_established = getattr(tracker_obj, "on_point_established", None)
    def pe_with_ledger(p: int) -> None:
        if original_point_established:
            original_point_established(p)
        ledger.begin_point_cycle()
    setattr(tracker_obj, "on_point_established", pe_with_ledger)

    # Both "point made" and "seven-out" end the cycle
    for end_hook_name in ("on_point_made", "on_seven_out"):
        original = getattr(tracker_obj, end_hook_name, None)
        if original is None:
            continue
        def _wrap(orig):
            def wrapped(*a, **k):
                res = orig(*a, **k)
                ledger.end_point_cycle()
                return res
            return wrapped
        setattr(tracker_obj, end_hook_name, _wrap(original))

    # --- Public API: placing & resolving bets ---
    def on_bet_placed(bet: str, amount: float, *, category: str | None = None, **meta: Any) -> int:
        return ledger.place(bet, amount, category=category, **meta)

    def on_bet_resolved(
        bet: str,
        *,
        result: str,
        payout: float = 0.0,
        entry_id: int | None = None,
        apply_to_bankroll: bool = False,
        **meta: Any,
    ):
        bankroll_hook = None
        if apply_to_bankroll and hasattr(tracker_obj, "on_bankroll_delta"):
            bankroll_hook = tracker_obj.on_bankroll_delta
        return ledger.resolve(
            bet,
            result=result,
            payout=payout,
            entry_id=entry_id,
            apply_to_bankroll=apply_to_bankroll,
            bankroll_hook=bankroll_hook,
            **meta,
        )

    setattr(tracker_obj, "on_bet_placed", on_bet_placed)
    setattr(tracker_obj, "on_bet_resolved", on_bet_resolved)

    # --- Snapshot extender (non-breaking) ---
    if hasattr(tracker_obj, "snapshot"):
        original_snapshot = tracker_obj.snapshot

        def snapshot_with_ledger() -> Dict[str, Any]:
            snap = original_snapshot()
            try:
                snap["ledger"] = ledger.snapshot()
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
                }
            return snap

        setattr(tracker_obj, "snapshot", snapshot_with_ledger)