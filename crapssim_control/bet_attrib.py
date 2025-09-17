"""
Bet-type attribution (Batch 5 + Batch 7 + Batch 9)

Batch 7 adds opportunity/exposure counters per bet type:
  placed_count, resolved_count, push_count, total_staked, exposure_rolls, peak_open_bets
Batch 9 canonicalizes keys via bet_types.normalize_bet_type to prevent fragmentation.

Snapshot shape (as expected by tests):
  snap["bet_attrib"]["by_bet_type"] = { <canon_type>: {counters...}, ... }
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from typing import Any, Dict, DefaultDict, Deque, Optional

from .bet_types import normalize_bet_type  # NEW


# -----------------------------
# Internal structures
# -----------------------------

@dataclass
class _PerTypeStats:
    # Batch 7 (opportunity/exposure)
    placed_count: int = 0
    resolved_count: int = 0
    push_count: int = 0
    total_staked: float = 0.0
    exposure_rolls: int = 0
    peak_open_bets: int = 0
    # Batch 5 (results)
    wins: int = 0
    losses: int = 0
    pnl: float = 0.0


def _coerce_str(event: Dict[str, Any], *keys: str, default: str = "") -> str:
    for k in keys:
        if k in event and event[k] is not None:
            return str(event[k])
    return default


def _coerce_float(event: Dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for k in keys:
        if k in event and event[k] is not None:
            try:
                return float(event[k])
            except Exception:
                pass
    return default


def _coerce_bool_outcome(event: Dict[str, Any]) -> Optional[bool]:
    """
    Normalize outcome → True (win) / False (loss) / None (push or unknown).
    Accepts fields like won/win/is_win/outcome/result/status.
    """
    # direct booleans first
    for k in ("won", "win", "is_win"):
        if k in event:
            v = event[k]
            if isinstance(v, bool):
                return v
            if isinstance(v, (int, float)):
                return bool(v)
            if isinstance(v, str):
                s = v.strip().lower()
                if s in ("true", "t", "1", "yes", "y"):
                    return True
                if s in ("false", "f", "0", "no", "n"):
                    return False
                if s == "push":
                    return None
    # string outcomes
    s = _coerce_str(event, "outcome", "result", "status", default="").strip().lower()
    if s in ("win", "won"):
        return True
    if s in ("loss", "lost", "lose"):
        return False
    if s == "push":
        return None
    return None


def _bet_key(event: Dict[str, Any]) -> str:
    """
    Canonical key for attribution buckets.

    Batch 9: prefer 'bet_type' if present (test fixtures use this),
    but ALWAYS normalize using the normalizer with number/context from event.
    """
    raw = _coerce_str(event, "bet_type", "bet", "type", default="").strip()
    canon = normalize_bet_type(raw, event)
    return canon or "unknown"


# -----------------------------
# Public API
# -----------------------------

def attach_bet_attrib(tracker: Any, enabled: Optional[bool] = None) -> None:
    """
    Monkey-patch a live Tracker with bet attribution + exposure counters.

    Adds:
      tracker.on_bet_placed(event)
      tracker.on_bet_resolved(event)
      tracker.on_bet_cleared(event)   # optional
    Wraps:
      tracker.on_roll(...) to accrue exposure for open bets
      tracker.snapshot()   to include 'bet_attrib' when enabled
    """
    # determine enablement
    if enabled is None:
        cfg = getattr(tracker, "config", {}) or {}
        enabled = bool(cfg.get("bet_attrib_enabled", True))
    tracker._bet_attrib_enabled = bool(enabled)

    # internal state on tracker
    if not hasattr(tracker, "_bet_stats"):
        tracker._bet_stats: DefaultDict[str, _PerTypeStats] = defaultdict(_PerTypeStats)
    if not hasattr(tracker, "_bet_open"):
        tracker._bet_open: DefaultDict[str, Deque[Dict[str, Any]]] = defaultdict(deque)

    # ------------- on_bet_placed --------------------------------------------

    def on_bet_placed(event: Dict[str, Any]) -> None:
        if not tracker._bet_attrib_enabled:
            return
        key = _bet_key(event)
        amt = _coerce_float(event, "amount", "stake", default=0.0)

        stats = tracker._bet_stats[key]
        stats.placed_count += 1
        stats.total_staked += float(amt)

        # track an open unit for exposure accrual
        opened_at_roll = _safe_roll_index(tracker)
        tracker._bet_open[key].append({"opened_at_roll": opened_at_roll, "amount": float(amt)})

        # peak concurrency per type
        if len(tracker._bet_open[key]) > stats.peak_open_bets:
            stats.peak_open_bets = len(tracker._bet_open[key])

    # ------------- on_bet_resolved ------------------------------------------

    def on_bet_resolved(event: Dict[str, Any]) -> None:
        if not tracker._bet_attrib_enabled:
            return
        key = _bet_key(event)
        outcome = _coerce_bool_outcome(event)

        # pnl handling
        pnl = _coerce_float(event, "pnl", default=None)
        if pnl is None:
            payout = _coerce_float(event, "payout", default=0.0)   # full return incl winnings
            amount = _coerce_float(event, "amount", "stake", default=0.0)
            pnl = payout - amount if (payout or amount) else 0.0

        stats = tracker._bet_stats[key]
        stats.resolved_count += 1

        if outcome is True:
            stats.wins += 1
            stats.pnl += float(pnl)
        elif outcome is False:
            stats.losses += 1
            stats.pnl += float(pnl)
        else:
            stats.push_count += 1
            stats.pnl += float(pnl)  # likely ~0, but preserve engine-provided value

        # close one open unit if present (LIFO)
        if tracker._bet_open[key]:
            tracker._bet_open[key].pop()

    # ------------- on_bet_cleared (optional) --------------------------------

    def on_bet_cleared(event: Dict[str, Any]) -> None:
        """
        Optional hook: if your engine emits a "clear" without resolve, close one open exposure unit.
        """
        if not tracker._bet_attrib_enabled:
            return
        key = _bet_key(event)
        if tracker._bet_open[key]:
            tracker._bet_open[key].pop()

    # ------------- on_roll wrapper (exposure accrual) ------------------------

    prev_on_roll = getattr(tracker, "on_roll", None)

    def on_roll_wrapper(*args, **kwargs):
        if tracker._bet_attrib_enabled:
            for key, stack in tracker._bet_open.items():
                if stack:
                    tracker._bet_stats[key].exposure_rolls += len(stack)
        if callable(prev_on_roll):
            return prev_on_roll(*args, **kwargs)

    if callable(prev_on_roll):
        setattr(tracker, "on_roll", on_roll_wrapper)

    # ------------- snapshot wrapper -----------------------------------------

    prev_snapshot = getattr(tracker, "snapshot")

    def snapshot_with_buckets(*args, **kwargs):
        snap = prev_snapshot(*args, **kwargs)
        if tracker._bet_attrib_enabled:
            by_type: Dict[str, Any] = {}
            for key, stats in tracker._bet_stats.items():
                by_type[key] = asdict(stats)
            snap["bet_attrib"] = {"by_bet_type": by_type}
        return snap

    # Patch hooks + snapshot
    setattr(tracker, "on_bet_placed", on_bet_placed)
    setattr(tracker, "on_bet_resolved", on_bet_resolved)
    setattr(tracker, "on_bet_cleared", on_bet_cleared)
    setattr(tracker, "snapshot", snapshot_with_buckets)


# -----------------------------
# Helpers
# -----------------------------

def _safe_roll_index(tracker: Any) -> int:
    try:
        return int(getattr(tracker, "roll").shooter_rolls)
    except Exception:
        return 0