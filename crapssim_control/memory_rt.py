# crapssim_control/memory_rt.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from collections import defaultdict, Counter


@dataclass
class SessionMemoryTracker:
    """
    Lightweight, in-RAM counters that summarize what happened in a single run.

    This tracker is intentionally inexpensive and resilient:
      - If disabled, all methods are no-ops.
      - No exceptions are raised out; best-effort tallying only.
      - Snapshot returns a single JSON-serializable dict.

    Tracked (MVP):
      • event_counts: comeout, point_established, roll, seven_out, summary
      • modes: per-event counts and number of changes
      • rules_fired: counts per rule id
      • bet_actions: set/press/reduce/clear counts per bet_type
      • switches: number of switch_mode actions
      • setvars: number of setvar actions
      • regression_clears: number of template-origin clears for regression
      • points_seen: histogram of established points
    """
    enabled: bool = True

    # event tallies
    event_counts: Counter = field(default_factory=Counter)
    points_seen: Counter = field(default_factory=Counter)

    # mode stats
    mode_event_counts: Counter = field(default_factory=Counter)
    mode_changes: int = 0
    _last_mode: Optional[str] = None

    # actions
    rules_fired: Counter = field(default_factory=Counter)
    bet_set: Counter = field(default_factory=Counter)
    bet_press: Counter = field(default_factory=Counter)
    bet_reduce: Counter = field(default_factory=Counter)
    bet_clear: Counter = field(default_factory=Counter)
    switches: int = 0
    setvars: int = 0
    regression_clears: int = 0

    def on_event(self, event: Dict[str, Any], *, mode: Optional[str], point: Optional[int], on_comeout: bool) -> None:
        if not self.enabled:
            return
        try:
            ev = str((event or {}).get("type", "")).strip().lower()
            self.event_counts[ev] += 1

            # point histogram
            if ev == "point_established":
                try:
                    pt = int((event or {}).get("point"))
                    if pt:
                        self.points_seen[pt] += 1
                except Exception:
                    pass

            # mode usage + change detection
            m = (mode or "").strip() or "Main"
            self.mode_event_counts[m] += 1
            if self._last_mode is None:
                self._last_mode = m
            elif self._last_mode != m:
                self.mode_changes += 1
                self._last_mode = m
        except Exception:
            # fail-open
            return

    def on_actions(self, actions: List[Dict[str, Any]], event: Dict[str, Any] | None = None) -> None:
        if not self.enabled or not actions:
            return
        try:
            for a in actions:
                src = str(a.get("source") or "").lower()
                act = str(a.get("action") or "").lower()
                bet = a.get("bet_type")

                # Count switches / setvars
                if act == "switch_mode":
                    self.switches += 1
                elif act == "setvar":
                    self.setvars += 1

                # Rules fired by id
                if src == "rule":
                    rid = str(a.get("id") or "").strip() or "rule:<unknown>"
                    self.rules_fired[rid] += 1

                # Bet actions per bet_type
                if isinstance(bet, str) and bet:
                    if act == "set":
                        self.bet_set[bet] += 1
                    elif act == "press":
                        self.bet_press[bet] += 1
                    elif act == "reduce":
                        self.bet_reduce[bet] += 1
                    elif act == "clear":
                        self.bet_clear[bet] += 1

                # Heuristic: regression clears (template source + known id)
                if act == "clear" and src == "template":
                    aid = str(a.get("id") or "")
                    if "regress_roll3" in aid:
                        self.regression_clears += 1
        except Exception:
            return

    def snapshot(self) -> Dict[str, Any]:
        """
        Return a compact JSON-serializable dict with the current tallies.
        """
        if not self.enabled:
            return {
                "enabled": False,
                "event_counts": {},
                "modes": {"counts": {}, "changes": 0},
                "rules_fired": {},
                "bets": {"set": {}, "press": {}, "reduce": {}, "clear": {}},
                "switches": 0,
                "setvars": 0,
                "regression_clears": 0,
                "points_seen": {},
            }

        return {
            "enabled": True,
            "event_counts": dict(self.event_counts),
            "modes": {
                "counts": dict(self.mode_event_counts),
                "changes": int(self.mode_changes),
            },
            "rules_fired": dict(self.rules_fired),
            "bets": {
                "set": dict(self.bet_set),
                "press": dict(self.bet_press),
                "reduce": dict(self.bet_reduce),
                "clear": dict(self.bet_clear),
            },
            "switches": int(self.switches),
            "setvars": int(self.setvars),
            "regression_clears": int(self.regression_clears),
            "points_seen": dict(self.points_seen),
        }