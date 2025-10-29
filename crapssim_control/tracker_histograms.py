# tracker_histograms.py
from __future__ import annotations
from typing import Any, Dict, Optional

INSIDE_SET = {5, 6, 8, 9}
OUTSIDE_SET = {4, 10, 6, 8}  # maintained for parity with prior language; 6/8 overlap by design


def _read_total_from_args(*args, **kwargs) -> Optional[int]:
    """
    Be liberal in what we accept:
      - on_roll(total: int)
      - on_roll(event: dict with {"total": int})
      - on_roll(..., total=int)
    """
    if "total" in kwargs and isinstance(kwargs["total"], (int, float)):
        return int(kwargs["total"])
    if args:
        # args[0] might be an int OR a dict/event with 'total'
        a0 = args[0]
        if isinstance(a0, (int, float)):
            return int(a0)
        if isinstance(a0, dict) and "total" in a0:
            try:
                return int(a0["total"])
            except Exception:
                return None
    return None


def _new_hist_dict() -> Dict[int, int]:
    # 2..12 inclusive
    return {n: 0 for n in range(2, 13)}


def attach_histograms(tracker: Any, enabled: Optional[bool] = None) -> None:
    """
    Batch 8 shim:
      - Tracks per-hand and per-shooter histograms of dice totals.
      - Resets hand histogram on seven-out.
      - Resets shooter histogram when shooter_id changes.
      - Exposes under snapshot()["history"] without breaking existing fields.

    Adds (attributes on tracker):
      _hist_enabled: bool
      _hand_hits: dict[int,int]
      _shooter_hits: dict[int,int]
      _session_hits: dict[int,int]  # created here if missing; we won't override an existing one
      _hand_inside_hits, _hand_outside_hits: int
      _shooter_inside_hits, _shooter_outside_hits: int
      _hist_last_shooter_id: any

    Wraps:
      on_roll(...)
      on_seven_out()           (if present)
      snapshot()
    """
    # enablement
    if enabled is None:
        cfg = getattr(tracker, "config", {}) or {}
        enabled = bool(cfg.get("hand_histograms_enabled", True))
    tracker._hist_enabled = bool(enabled)

    # init counters
    if not hasattr(tracker, "_hand_hits"):
        tracker._hand_hits = _new_hist_dict()
    if not hasattr(tracker, "_shooter_hits"):
        tracker._shooter_hits = _new_hist_dict()
    # don't clobber an existing session-wide dict if you already maintain one
    if not hasattr(tracker, "_session_hits"):
        tracker._session_hits = _new_hist_dict()

    tracker._hand_inside_hits = getattr(tracker, "_hand_inside_hits", 0)
    tracker._hand_outside_hits = getattr(tracker, "_hand_outside_hits", 0)
    tracker._shooter_inside_hits = getattr(tracker, "_shooter_inside_hits", 0)
    tracker._shooter_outside_hits = getattr(tracker, "_shooter_outside_hits", 0)

    tracker._hist_last_shooter_id = getattr(tracker, "shooter_id", None)

    # ---- helpers to reset layers ------------------------------------------
    def _reset_hand_layer():
        tracker._hand_hits = _new_hist_dict()
        tracker._hand_inside_hits = 0
        tracker._hand_outside_hits = 0

    def _reset_shooter_layer():
        tracker._shooter_hits = _new_hist_dict()
        tracker._shooter_inside_hits = 0
        tracker._shooter_outside_hits = 0

    tracker.reset_hand_hist = _reset_hand_layer
    tracker.reset_shooter_hist = _reset_shooter_layer

    # ---- wrap on_roll -------------------------------------------------------
    prev_on_roll = getattr(tracker, "on_roll", None)

    def on_roll_wrapper(*args, **kwargs):
        if tracker._hist_enabled:
            # detect shooter change opportunistically (some engines only bump shooter_id outside explicit hooks)
            current_sid = getattr(tracker, "shooter_id", None)
            if current_sid != tracker._hist_last_shooter_id:
                _reset_shooter_layer()
                tracker._hist_last_shooter_id = current_sid

            total = _read_total_from_args(*args, **kwargs)
            if isinstance(total, int) and 2 <= total <= 12:
                # increment three layers (session assumed safe here)
                tracker._hand_hits[total] = tracker._hand_hits.get(total, 0) + 1
                tracker._shooter_hits[total] = tracker._shooter_hits.get(total, 0) + 1
                # if the host has its own session counters, prefer those; else maintain our local
                if hasattr(tracker, "hits") and isinstance(tracker.hits, dict):
                    tracker.hits[total] = tracker.hits.get(total, 0) + 1
                else:
                    tracker._session_hits[total] = tracker._session_hits.get(total, 0) + 1

                # inside/outside mirrors
                if total in INSIDE_SET:
                    tracker._hand_inside_hits += 1
                    tracker._shooter_inside_hits += 1
                if total in OUTSIDE_SET:
                    tracker._hand_outside_hits += 1
                    tracker._shooter_outside_hits += 1

        if callable(prev_on_roll):
            return prev_on_roll(*args, **kwargs)

    if callable(prev_on_roll):
        setattr(tracker, "on_roll", on_roll_wrapper)

    # ---- wrap seven-out reset if available ---------------------------------
    for seven_hook_name in ("on_seven_out", "on_point_seven_out", "on_hand_end"):
        prev = getattr(tracker, seven_hook_name, None)
        if callable(prev):

            def make_wrapper(prev_func):
                def _wrap(*a, **k):
                    if tracker._hist_enabled:
                        _reset_hand_layer()
                    return prev_func(*a, **k)

                return _wrap

            setattr(tracker, seven_hook_name, make_wrapper(prev))

    # ---- snapshot wrapper ---------------------------------------------------
    prev_snapshot = getattr(tracker, "snapshot")

    def snapshot_with_hist(*args, **kwargs):
        snap = prev_snapshot(*args, **kwargs)
        if tracker._hist_enabled:
            # choose the best session dict to display
            session_hits = tracker.hits if hasattr(tracker, "hits") else tracker._session_hits
            snap.setdefault("history", {})
            snap["history"].update(
                {
                    "hand_hits": {str(k): int(v) for k, v in tracker._hand_hits.items()},
                    "shooter_hits": {str(k): int(v) for k, v in tracker._shooter_hits.items()},
                    "session_hits": {str(k): int(v) for k, v in session_hits.items()},
                    "hand_inside_hits": int(tracker._hand_inside_hits),
                    "hand_outside_hits": int(tracker._hand_outside_hits),
                    "shooter_inside_hits": int(tracker._shooter_inside_hits),
                    "shooter_outside_hits": int(tracker._shooter_outside_hits),
                }
            )
        return snap

    setattr(tracker, "snapshot", snapshot_with_hist)
