"""
Bet-type attribution (Batch 5)

Non-invasive add-on that augments an existing Tracker instance with:
  - on_bet_placed(event: dict) -> None          # reserved/hook; no logic yet
  - on_bet_resolved(event: dict) -> None        # updates per-type wins/losses/pnl
  - snapshot() wrapper that injects a 'bet_attrib' block (when enabled)

Enable either by:
  - Passing enabled explicitly to attach_bet_attrib(tracker, enabled=True), or
  - Setting tracker.config.get("bet_attrib_enabled") to True (if your Tracker preserves it)

This module does NOT mutate bankroll or core game logic. It's purely accounting.
"""

from __future__ import annotations

from collections import defaultdict
from types import MethodType
from typing import Any, Dict, Optional


def _coerce_str(d: Dict[str, Any], *keys: str, default: str = "unknown") -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return default


def _coerce_float(d: Dict[str, Any], *keys: str) -> Optional[float]:
    for k in keys:
        if k in d:
            try:
                return float(d[k])
            except (TypeError, ValueError):
                pass
    return None


def _coerce_bool(d: Dict[str, Any], *keys: str) -> Optional[bool]:
    for k in keys:
        if k in d:
            v = d[k]
            if isinstance(v, bool):
                return v
            if isinstance(v, (int, float)):
                return bool(v)
            if isinstance(v, str):
                s = v.strip().lower()
                if s in ("win", "won", "true", "yes", "y", "1"):
                    return True
                if s in ("loss", "lost", "false", "no", "n", "0"):
                    return False
    return None


def attach_bet_attrib(tracker: Any, *, enabled: Optional[bool] = None) -> None:
    """
    Monkey-patch a Tracker instance with bet attribution hooks & snapshot injection.
    This is instance-level (safe), not class-wide.

    Args:
        tracker: an instance of Tracker
        enabled: optionally force-enable/disable attribution. If None, falls back to
                 tracker.config.get("bet_attrib_enabled", False)
    """
    # Resolve enabled flag
    if enabled is None:
        cfg = getattr(tracker, "config", {}) or {}
        enabled = bool(cfg.get("bet_attrib_enabled", False))
    enabled = bool(enabled)

    # Internal storage (per instance)
    store = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0})

    # Keep original snapshot for chaining
    orig_snapshot = tracker.snapshot

    def _snapshot_with_bet_attrib(self) -> Dict[str, Any]:
        snap = orig_snapshot()
        if enabled:
            by_type_plain: Dict[str, Dict[str, Any]] = {
                k: {"wins": v["wins"], "losses": v["losses"], "pnl": float(v["pnl"])}
                for k, v in store.items()
            }
            snap["bet_attrib"] = {"by_bet_type": by_type_plain}
        else:
            snap.pop("bet_attrib", None)
        return snap

    def _on_bet_placed(self, event: Dict[str, Any]) -> None:
        # Reserved for future (exposure tracking). Intentionally no-op for stability.
        _ = event
        return

    def _on_bet_resolved(self, event: Dict[str, Any]) -> None:
        if not enabled:
            return

        bet_type = _coerce_str(event, "bet_type", "type")

        pnl = _coerce_float(event, "pnl", "delta", "net")
        if pnl is None:
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

            if won is None:
                pnl = 0.0
            else:
                amt = _coerce_float(event, "amount", "risk", "stake") or 1.0
                pnl = amt if won else -amt

        bucket = store[bet_type]
        if pnl > 0:
            bucket["wins"] += 1
        elif pnl < 0:
            bucket["losses"] += 1
        bucket["pnl"] = float(bucket["pnl"]) + float(pnl)

    # Bind to *this* instance only
    tracker.on_bet_placed = MethodType(_on_bet_placed, tracker)
    tracker.on_bet_resolved = MethodType(_on_bet_resolved, tracker)
    tracker.snapshot = MethodType(_snapshot_with_bet_attrib, tracker)

    # Debug hooks (optional)
    tracker._bet_attrib_enabled = enabled
    tracker._bet_attrib_store = store
    tracker._bet_attrib_snapshot_wrapped = orig_snapshot