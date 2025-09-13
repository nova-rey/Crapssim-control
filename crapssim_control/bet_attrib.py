"""
Bet-type attribution (Batch 5)

Non-invasive add-on that augments an existing Tracker instance with:
  - on_bet_placed(event: dict) -> None          # reserved/hook; no logic yet
  - on_bet_resolved(event: dict) -> None        # updates per-type wins/losses/pnl
  - snapshot() wrapper that injects a 'bet_attrib' block (when enabled)

Enable via tracker config:
  Tracker({"enabled": True, "bet_attrib_enabled": True})

Expected event shape (lenient):
  - event for resolution should have:
      bet_type: str            (or 'type')
      pnl: float               (or 'delta' or 'net'; if absent -> inferred from win/loss)
      outcome: 'win'|'loss'|'push' (or 'result', 'status', 'won' bool); optional

If 'pnl' is absent, we infer from outcome:
  win  -> +abs(amount or 1.0)
  loss -> -abs(amount or 1.0)
  push -> 0.0
We do NOT mutate bankroll here--this is read-only attribution.

To use:
  from crapssim_control.bet_attrib import attach_bet_attrib
  tr = Tracker({"enabled": True, "bet_attrib_enabled": True})
  attach_bet_attrib(tr)
  tr.on_bet_resolved({...})
  snap = tr.snapshot()
  snap["bet_attrib"]["by_bet_type"] -> dict
"""

from __future__ import annotations

from collections import defaultdict
from types import MethodType
from typing import Any, Dict, Optional, Tuple


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


def attach_bet_attrib(tracker: Any) -> None:
    """
    Monkey-patch a Tracker instance with bet attribution hooks & snapshot injection.
    This is instance-level (safe), not class-wide.
    """
    # Respect feature flag on tracker.config if present
    cfg = getattr(tracker, "config", {}) or {}
    enabled = bool(cfg.get("bet_attrib_enabled", False))

    # Internal storage (per instance)
    store = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0})

    # Keep original snapshot for chaining
    orig_snapshot = tracker.snapshot

    def _snapshot_with_bet_attrib(self) -> Dict[str, Any]:
        snap = orig_snapshot()
        if enabled:
            # Convert defaultdict -> plain dict with shallow copies to avoid accidental mutation by callers
            by_type_plain: Dict[str, Dict[str, Any]] = {
                k: {"wins": v["wins"], "losses": v["losses"], "pnl": float(v["pnl"])}
                for k, v in store.items()
            }
            snap["bet_attrib"] = {"by_bet_type": by_type_plain}
        else:
            # When disabled, do NOT add the key at all (clean no-op)
            snap.pop("bet_attrib", None)
        return snap

    def _on_bet_placed(self, event: Dict[str, Any]) -> None:
        # Reserved; we may later track exposure. For now, no-op to keep behavior predictable.
        _ = event
        return

    def _on_bet_resolved(self, event: Dict[str, Any]) -> None:
        if not enabled:
            return

        # Extract bet_type
        bet_type = _coerce_str(event, "bet_type", "type")

        # Determine pnl
        pnl = _coerce_float(event, "pnl", "delta", "net")
        if pnl is None:
            # Infer from outcome or 'won' flag
            won: Optional[bool] = _coerce_bool(event, "won", "win", "is_win")
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
                amt = _coerce_float(event, "amount", "risk", "stake") or 0.0
                pnl = 0.0  # unknown → treat as neutral
            else:
                amt = _coerce_float(event, "amount", "risk", "stake") or 1.0
                pnl = amt if won else -amt

        # Tally
        bucket = store[bet_type]
        if pnl > 0:
            bucket["wins"] += 1
        elif pnl < 0:
            bucket["losses"] += 1
        # pushes (pnl == 0) do not increment wins/losses
        bucket["pnl"] = float(bucket["pnl"]) + float(pnl)

    # Bind to *this* instance only
    tracker.on_bet_placed = MethodType(_on_bet_placed, tracker)
    tracker.on_bet_resolved = MethodType(_on_bet_resolved, tracker)
    tracker.snapshot = MethodType(_snapshot_with_bet_attrib, tracker)

    # Stash references (optional, for debugging/detach if ever needed)
    tracker._bet_attrib_enabled = enabled
    tracker._bet_attrib_store = store
    tracker._bet_attrib_snapshot_wrapped = orig_snapshot