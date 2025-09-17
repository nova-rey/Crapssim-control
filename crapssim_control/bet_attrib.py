"""
Bet-type attribution (Batch 5 + Batch 7)

This module augments a live Tracker instance with:
  - on_bet_placed(event: dict) -> None
  - on_bet_resolved(event: dict) -> None
  - (optional) on_bet_cleared(event: dict) -> None   # if your engine emits clears without a resolve
  - snapshot() wrapper that injects a 'bet_attrib' block when enabled

Batch 7 adds exposure & opportunity tracking per bet type:
  placed_count, resolved_count, push_count, total_staked, exposure_rolls, peak_open_bets
…while preserving Batch 5: wins, losses, pnl.

Enable either by:
  - attach_bet_attrib(tracker, enabled=True)
  - or set tracker.config.get("bet_attrib_enabled") to True (if your Tracker preserves config)

This module does NOT mutate bankroll or core game logic. It's purely accounting.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from typing import Any, Dict, DefaultDict, Deque, Optional


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


def _coerce_bool(event: Dict[str, Any], *keys: str) -> Optional[bool]:
    for k in keys:
        if k in event:
            v = event[k]
            if isinstance(v, bool):
                return v
            if isinstance(v, str):
                s = v.strip().lower()
                if s in ("true", "t", "1", "yes", "y", "win", "won"):
                    return True
                if s in ("false", "f", "0", "no", "n", "loss", "lost", "lose"):
                    return False
                if s == "push":
                    return None
            if isinstance(v, (int, float)):
                return bool(v)
    return None


def _bet_key(event: Dict[str, Any]) -> str:
    """
    Canonical key for attribution buckets.

    NOTE: We intentionally do NOT include the number here yet (e.g., 6 vs 8)
    to avoid fragmenting stats before Batch 9 normalization/taxonomy.
    Engines should pass a stable 'bet' string such as 'place', 'odds', 'pass'.
    """
    b = _coerce_str(event, "bet", "type", default="").strip().lower()
    return b or "unknown"


# -----------------------------
# Public API
# -----------------------------

def attach_bet_attrib(tracker: Any, enabled: Optional[bool] = None) -> None:
    """
    Monkey-patch a live Tracker with bet attribution + exposure counters.

    Adds:
      tracker.on_bet_placed(event)
      tracker.on_bet_resolved(event)
      tracker.on_bet_cleared(event)   # optional; safe if never called
    Wraps:
      tracker.on_roll(...) to accrue exposure for open bets
      tracker.snapshot() to include 'bet_attrib' when enabled
    """
    # Determine enablement
    if enabled is None:
        cfg = getattr(tracker, "config", {}) or {}
        enabled = bool(cfg.get("bet_attrib_enabled", True))  # default True if unspecified
    tracker._bet_attrib_enabled = bool(enabled)

    # Internal state containers on the tracker
    if not hasattr(tracker, "_bet_stats"):
        tracker._bet_stats: DefaultDict[str, _PerTypeStats] = defaultdict(_PerTypeStats)
    if not hasattr(tracker, "_bet_open"):
        # per bet-type, a stack of open entries (we track one unit per placement)
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

        # Push an "open position" record (we track exposure from on_roll)
        opened_at_roll = _safe_roll_index(tracker)
        tracker._bet_open[key].append({"opened_at_roll": opened_at_roll, "amount": float(amt)})

        # Peak concurrency per type
        open_count = len(tracker._bet_open[key])
        if open_count > stats.peak_open_bets:
            stats.peak_open_bets = open_count

    # ------------- on_bet_resolved ------------------------------------------

    def on_bet_resolved(event: Dict[str, Any]) -> None:
        if not tracker._bet_attrib_enabled:
            return
        key = _bet_key(event)

        # Outcome normalization
        won = _coerce_bool(event, "won", "win", "is_win")
        if won is None:
            outcome = _coerce_str(event, "outcome", "result", "status", default="")
            if outcome.lower() in ("win", "won"):
                won = True
            elif outcome.lower() in ("loss", "lost", "lose"):
                won = False
            elif outcome.lower() == "push":
                won = None
            else:
                won = None

        pnl = _coerce_float(event, "pnl", default=None)
        if pnl is None:
            # payout is the full return incl. winnings; if engine sends both
            payout = _coerce_float(event, "payout", default=0.0)
            amount = _coerce_float(event, "amount", "stake", default=0.0)
            # If engine doesn't provide amount here, we won't compute pnl precisely.
            # It’s okay: Batch 5 tests typically pass pnl explicitly, but we fall back.
            pnl = payout - amount if payout or amount else 0.0

        stats = tracker._bet_stats[key]
        stats.resolved_count += 1

        if won is True:
            stats.wins += 1
            stats.pnl += float(pnl)
        elif won is False:
            stats.losses += 1
            stats.pnl += float(pnl)  # negative expected if loss
        else:
            # push
            stats.push_count += 1
            # no wins/losses change; pnl should be ~0 (but we add whatever came in)

        # Close one open entry if present (LIFO)
        if tracker._bet_open[key]:
            tracker._bet_open[key].pop()

    # ------------- on_bet_cleared (optional) --------------------------------

    def on_bet_cleared(event: Dict[str, Any]) -> None:
        """
        Optional hook: if your engine emits a "clear" without resolve (e.g., take down a Place bet),
        treat it as closing one open exposure unit without changing wins/losses/pnl.
        """
        if not tracker._bet_attrib_enabled:
            return
        key = _bet_key(event)
        if tracker._bet_open[key]:
            tracker._bet_open[key].pop()

    # ------------- on_roll wrapper (exposure accrual) ------------------------

    prev_on_roll = getattr(tracker, "on_roll", None)

    def on_roll_wrapper(*args, **kwargs):
        # Best-effort exposure accrual: +1 per open instance per roll
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
            # Convert to plain dict for snapshot stability
            out: Dict[str, Any] = {}
            for key, stats in tracker._bet_stats.items():
                out[key] = asdict(stats)
            snap["bet_attrib"] = out
        return snap

    setattr(tracker, "on_bet_placed", on_bet_placed)
    setattr(tracker, "on_bet_resolved", on_bet_resolved)
    setattr(tracker, "on_bet_cleared", on_bet_cleared)
    setattr(tracker, "snapshot", snapshot_with_buckets)


# -----------------------------
# Helpers
# -----------------------------

def _safe_roll_index(tracker: Any) -> int:
    """
    Attempts to read a roll index from the tracker for debugging; returns 0 if unavailable.
    """
    try:
        return int(getattr(tracker, "roll").shooter_rolls)
    except Exception:
        return 0