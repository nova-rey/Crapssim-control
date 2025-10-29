"""
Bet-type attribution
(Batch 5 + Batch 7 + Batch 9 + Batch 10)

What this module provides:
  - Hooks to attribute results + opportunity/exposure to bet types
  - Canonical bet-type keys (via bet_types.normalize_bet_type)
  - Batch 10 computed rates and richer metadata aggregation

Per bet type we track raw counters (B5/B7):
  placed_count, resolved_count, push_count,
  total_staked, exposure_rolls, peak_open_bets,
  wins, losses, pnl  (pnl is NET, see commission handling below)

NEW in Batch 10 (fields added to each bet type snapshot):
  - total_commission         (sum of commission/vig/fee provided on events)
  - hit_rate                 = wins / max(1, resolved_count - push_count)
  - roi                      = pnl / max(1, total_staked)
  - pnl_per_exposure_roll    = pnl / max(1, exposure_rolls)

Optional event fields that are consumed if present:
  - 'commission' | 'vig' | 'fee'  (float)   → subtracted from pnl and tallied into total_commission
  - 'working_on_comeout'          (bool)    → recorded on resolution for context counts (lightweight)
  - 'odds_multiple'               (float)   → accepted but not aggregated yet (reserved for future)
  - 'point_number'                (int)     → accepted; not aggregated here (you can export from ledger)

Snapshot shape (unchanged at the top level for compatibility):
  snap["bet_attrib"]["by_bet_type"] = {
      <canon_type>: {
          placed_count, resolved_count, push_count,
          total_staked, exposure_rolls, peak_open_bets,
          wins, losses, pnl, total_commission,
          hit_rate, roi, pnl_per_exposure_roll,
          _ctx: { "comeout_resolved": x, "point_resolved": y }  # optional context counters
      }, ...
  }
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from typing import Any, Dict, DefaultDict, Deque, Optional

from .bet_types import normalize_bet_type


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
    # Batch 10 (rich meta)
    total_commission: float = 0.0
    # lightweight context counters (Batch 10)
    comeout_resolved: int = 0
    point_resolved: int = 0


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


def _coerce_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("true", "t", "1", "yes", "y"):
            return True
        if s in ("false", "f", "0", "no", "n"):
            return False
        if s == "push":
            return None
    return None


def _coerce_bool_outcome(event: Dict[str, Any]) -> Optional[bool]:
    # Direct booleans first
    for k in ("won", "win", "is_win"):
        if k in event:
            b = _coerce_bool(event[k])
            if b is not None:
                return b
    # String outcomes
    s = _coerce_str(event, "outcome", "result", "status", default="").strip().lower()
    if s in ("win", "won"):
        return True
    if s in ("loss", "lost", "lose"):
        return False
    if s == "push":
        return None
    return None


def _bet_key(event: Dict[str, Any]) -> str:
    # Prefer explicit bet_type, else bet/type; always normalize
    raw = _coerce_str(event, "bet_type", "bet", "type", default="").strip()
    canon = normalize_bet_type(raw, event)
    return canon or "unknown"


# -----------------------------
# Public API
# -----------------------------


def attach_bet_attrib(tracker: Any, enabled: Optional[bool] = None) -> None:
    """
    Monkey-patch a live Tracker with bet attribution + exposure counters + Batch 10 rates.

    Adds:
      tracker.on_bet_placed(event)
      tracker.on_bet_resolved(event)
      tracker.on_bet_cleared(event)   # optional
    Wraps:
      tracker.on_roll(...) to accrue exposure for open bets
      tracker.snapshot()   to include 'bet_attrib' (with computed rates) when enabled
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
        # store minimal meta in case we want to expand context later
        tracker._bet_open[key].append(
            {
                "opened_at_roll": opened_at_roll,
                "amount": float(amt),
            }
        )

        # peak concurrency per type
        if len(tracker._bet_open[key]) > stats.peak_open_bets:
            stats.peak_open_bets = len(tracker._bet_open[key])

    # ------------- on_bet_resolved ------------------------------------------

    def on_bet_resolved(event: Dict[str, Any]) -> None:
        if not tracker._bet_attrib_enabled:
            return
        key = _bet_key(event)
        outcome = _coerce_bool_outcome(event)

        # commission/vig handling (Batch 10)
        commission = _coerce_float(event, "commission", "vig", "fee", default=0.0)

        # pnl handling: if 'pnl' provided, treat it as gross; subtract commission.
        pnl = _coerce_float(event, "pnl", default=None)
        if pnl is None:
            payout = _coerce_float(event, "payout", default=0.0)  # full return incl winnings
            amount = _coerce_float(event, "amount", "stake", default=0.0)
            pnl = payout - amount
        net_pnl = float(pnl) - float(commission)

        stats = tracker._bet_stats[key]
        stats.resolved_count += 1
        stats.total_commission += float(commission)

        # Lightweight context recording (count only; does not split exposure)
        woc = event.get("working_on_comeout")
        woc_b = _coerce_bool(woc)
        if woc_b is True:
            stats.comeout_resolved += 1
        elif woc_b is False:
            stats.point_resolved += 1

        if outcome is True:
            stats.wins += 1
            stats.pnl += net_pnl
        elif outcome is False:
            stats.losses += 1
            stats.pnl += net_pnl
        else:
            stats.push_count += 1
            stats.pnl += net_pnl  # usually ~0 after commission, but keep engine-provided value

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
                row = asdict(stats)
                # Derived metrics (Batch 10)
                denom_resolved_no_push = max(1, stats.resolved_count - stats.push_count)
                row["hit_rate"] = float(stats.wins) / float(denom_resolved_no_push)
                row["roi"] = float(stats.pnl) / float(max(1.0, stats.total_staked))
                row["pnl_per_exposure_roll"] = float(stats.pnl) / float(
                    max(1, stats.exposure_rolls)
                )
                # Present context as a nested, clearly named block
                row["_ctx"] = {
                    "comeout_resolved": stats.comeout_resolved,
                    "point_resolved": stats.point_resolved,
                }
                by_type[key] = row
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
