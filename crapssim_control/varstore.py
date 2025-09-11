from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class VarStore:
    """
    Holds user variables ("variables" block from the spec) and lightweight
    system/tracking variables that the rules engine and controller can read.

    This class is intentionally simple and tolerant of missing data so it
    remains test-friendly and engine-agnostic.
    """

    # User variables (from the spec)
    variables: Dict[str, Any] = field(default_factory=dict)

    # System vars are derived from table snapshots/events
    system: Dict[str, Any] = field(default_factory=dict)

    # Tracking counters (lightweight; safe defaults)
    counters: Dict[str, Any] = field(default_factory=dict)

    # Last bankroll we observed (to compute deltas per roll if desired)
    _last_bankroll: Optional[float] = None

    # -----------------------------
    # Construction helpers
    # -----------------------------
    @classmethod
    def from_spec(cls, spec: Dict[str, Any]) -> "VarStore":
        vars_block = dict(spec.get("variables") or {})
        vs = cls(variables=vars_block)
        vs._ensure_defaults()
        return vs

    def _ensure_defaults(self) -> None:
        # System defaults used in tests and rules
        sysd = self.system
        sysd.setdefault("rolls_since_point", 0)
        sysd.setdefault("point_number", None)
        sysd.setdefault("comeout", True)

        # Tracking counters -- non-intrusive defaults
        ctr = self.counters
        # Hits by box/prop total 2..12
        ctr.setdefault("number_hits", {n: 0 for n in range(2, 13)})
        # Field (2,3,4,9,10,11,12 are typical; table may vary)
        ctr.setdefault("field_hits", 0)
        ctr.setdefault("field_losses", 0)
        # Hardways (4,6,8,10)
        ctr.setdefault("hardway_hits", {n: 0 for n in (4, 6, 8, 10)})
        ctr.setdefault("hardway_losses", {n: 0 for n in (4, 6, 8, 10)})
        # Point lifecycle
        ctr.setdefault("points_established", 0)
        ctr.setdefault("points_made", 0)
        # Seven-outs
        ctr.setdefault("seven_outs", 0)

    # -----------------------------
    # Snapshot-driven updates
    # -----------------------------
    def refresh_system(self, curr_snapshot: Any) -> None:
        """
        Update system variables from the current snapshot only.
        This keeps the original behavior the tests rely on.

        Expected minimal shape for curr_snapshot:
          - .table.comeout : bool
          - .table.point_number : Optional[int]
          - .table.point_on : bool
          - .table.roll_index : int (optional)
          - .player.bankroll : float (optional)
          - .table.dice : tuple like (d1, d2, total) (optional)
        """
        self._ensure_defaults()

        table = getattr(curr_snapshot, "table", None)

        comeout = getattr(table, "comeout", self.system.get("comeout", True))
        point_num = getattr(table, "point_number", None)
        point_on = getattr(table, "point_on", False)

        # Maintain rolls_since_point using current point context only.
        # If point is on and we have a roll index change upstream, tests
        # will call this once per roll so increment on any under-point roll.
        if point_on and point_num:
            # If a point is active, "this roll" counts toward rolls_since_point,
            # UNLESS it's exactly the establishing roll (the tests set that to 0 elsewhere).
            # We leave the exact zeroing to event-side-effects (see apply_event_side_effects).
            self.system["rolls_since_point"] = int(self.system.get("rolls_since_point", 0))
        else:
            # When point is off, keep the counter as-is; event hooks will reset.
            self.system["rolls_since_point"] = int(self.system.get("rolls_since_point", 0))

        # Update cached comeout/point
        self.system["comeout"] = bool(comeout)
        self.system["point_number"] = point_num

        # Opportunistic, non-breaking tracking by total (if present)
        dice = getattr(table, "dice", None)
        if isinstance(dice, (tuple, list)) and len(dice) >= 3:
            total = dice[2]
            if isinstance(total, int) and 2 <= total <= 12:
                self._bump_number_hit(total)
                self._maybe_bump_field(total)
                self._maybe_bump_hardways(dice)

        # Bankroll tracking (optional)
        player = getattr(curr_snapshot, "player", None)
        bankroll = getattr(player, "bankroll", None)
        if isinstance(bankroll, (int, float)):
            self._last_bankroll = float(bankroll)

    # -----------------------------
    # Event-side effects
    # -----------------------------
    def apply_event_side_effects(self, event: Dict[str, Any], curr_snapshot: Any) -> None:
        """
        Adjust counters based on the derived event while keeping tests happy.
        This is called by the controller after it derives the event.
        """
        self._ensure_defaults()
        name = (event or {}).get("event")

        if name == "point_established":
            # Reset rolls_since_point to zero at establishment
            self.system["rolls_since_point"] = 0
            self.counters["points_established"] += 1
            # Cache point number if provided
            p = event.get("point")
            if p:
                self.system["point_number"] = p

        elif name == "roll":
            # If we're under a point, increment rolls_since_point
            table = getattr(curr_snapshot, "table", None)
            point_on = getattr(table, "point_on", False)
            point_num = getattr(table, "point_number", None)
            if point_on and point_num:
                self.system["rolls_since_point"] = int(self.system.get("rolls_since_point", 0)) + 1

        elif name == "point_made":
            # Point was hit (pass resolves win). Reset counter and bump points_made.
            self.counters["points_made"] += 1
            self.system["rolls_since_point"] = 0
            self.system["point_number"] = None

        elif name == "seven_out":
            # Hand ended; reset counter, clear point, bump seven-outs
            self.counters["seven_outs"] += 1
            self.system["rolls_since_point"] = 0
            self.system["point_number"] = None

        elif name == "comeout":
            # Just mark that we're on comeout; counter remains at whatever last state was.
            self.system["comeout"] = True

    # -----------------------------
    # Lightweight counter helpers
    # -----------------------------
    def _bump_number_hit(self, total: int) -> None:
        nh = self.counters.get("number_hits")
        if isinstance(nh, dict) and total in nh:
            nh[total] += 1

    def _maybe_bump_field(self, total: int) -> None:
        # Typical field numbers: 2,3,4,9,10,11,12
        if total in (2, 3, 4, 9, 10, 11, 12):
            self.counters["field_hits"] += 1
        else:
            # Non-field totals count as a "field loss" if you had a field bet,
            # but since we don't inspect live bets here, just count them as
            # potential losses for high-level rates. This is optional and
            # harmless if unused.
            self.counters["field_losses"] += 1

    def _maybe_bump_hardways(self, dice: Any) -> None:
        # Expect (d1, d2, total)
        try:
            d1, d2, total = int(dice[0]), int(dice[1]), int(dice[2])
        except Exception:
            return

        if total not in (4, 6, 8, 10):
            return

        if d1 == d2:
            # Hardway hit for that box number
            self.counters["hardway_hits"][total] += 1
        else:
            # "Soft" for that box number: counts as hardway loss if one were up.
            self.counters["hardway_losses"][total] += 1