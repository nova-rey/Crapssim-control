# crapssim_control/tracker.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple

# ----------------------------
# Config defaults & families
# ----------------------------

FAMILIES = (
    # Line
    "pass", "dont_pass",
    # Come
    "come", "dont_come",
    # Numbered flats & place/buy/lay by box number
    "place", "buy", "lay",
    # Center action
    "field", "hardway", "horn", "any_craps", "any_seven",
    # Catch-all for side/prop you may add later
    "prop",
)

DEFAULT_TRACKING_CFG = {
    "enabled": False,
    "scopes": ["session"],              # "session", "shooter"
    "reset_shooter_on": "seven_out",    # or "point_resolved"
    "roll_hits": True,                  # maintain hit_counts[2..12]
    "bankroll": True,                   # maintain peak/drawdown
    "odds_breakout": True,              # separate flat vs odds fields in aggregates
    "ledger": False,                    # keep in-memory event list (no I/O here)
    # Aggregation toggles
    "families": {f: True for f in FAMILIES},
    "by_number": True,                  # maintain per-number splits where applicable
}


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    out.update(b or {})
    return out


# ----------------------------
# Aggregate structures
# ----------------------------

def _empty_totals(odds_breakout: bool) -> Dict[str, float]:
    base = {
        "bets": 0,          # count of settled bets (regardless of outcome)
        "wins": 0,
        "losses": 0,
        "pushes": 0,
        "net": 0.0,         # flat+odds net delta
        "stake": 0.0,       # optional: sum of (flat_stake + odds_stake) when provided
        "flat_delta": 0.0,
        "odds_delta": 0.0,
    }
    if not odds_breakout:
        # flatten later, but keep same keys for simplicity
        pass
    return base


def _touch_agg_root(agg: Dict[str, Any], family: str, odds_breakout: bool):
    if family not in agg:
        agg[family] = _empty_totals(odds_breakout)
    if "__by_number__" not in agg:
        agg["__by_number__"] = {}
    if family not in agg["__by_number__"]:
        agg["__by_number__"][family] = {}  # number -> totals


def _agg_for(agg: Dict[str, Any], family: str, number: Optional[int], odds_breakout: bool) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Return (family_totals, per_number_totals_or_None)."""
    _touch_agg_root(agg, family, odds_breakout)
    fam_totals = agg[family]
    num_totals = None
    if number is not None:
        byn = agg["__by_number__"][family]
        if number not in byn:
            byn[number] = _empty_totals(odds_breakout)
        num_totals = byn[number]
    return fam_totals, num_totals


# ----------------------------
# Tracker (Phase A + Phase B)
# ----------------------------

@dataclass
class Tracker:
    """Session/shooter/roll/point/bankroll & aggregates.

    Phase A (already wired):
      - roll: last_roll, roll_index, shooter_rolls, rolls_since_point
      - point: point, point_cycle
      - bankroll: bankroll, bankroll_peak, drawdown, max_drawdown, pnl_since_shooter, pnl_since_point
      - hits: hit_counts[2..12]

    Phase B (new):
      - aggregates (session & shooter): per-family and [optionally] per-number totals
        fields: bets, wins, losses, pushes, net, stake, flat_delta, odds_delta
      - simple in-memory ledger (disabled by default)
    """
    cfg: Dict[str, Any] = field(default_factory=dict)

    # roll scope
    last_roll: int = 0
    roll_index: int = 0
    shooter_rolls: int = 0
    rolls_since_point: int = 0

    # point scope
    point: int = 0  # 0/None means off
    point_cycle: int = 0

    # bankroll scope
    bankroll: float = 0.0
    bankroll_peak: float = 0.0
    drawdown: float = 0.0
    max_drawdown: float = 0.0
    pnl_since_shooter: float = 0.0
    pnl_since_point: float = 0.0

    # hits
    hit_counts: Dict[int, int] = field(default_factory=lambda: {n: 0 for n in range(2, 13)})

    # shooter/session indices
    shooter_index: int = 1
    shooter_count: int = 0
    hands_played: int = 0
    seven_outs: int = 0
    points_made: int = 0

    # aggregates
    agg_session: Dict[str, Any] = field(default_factory=dict)   # family -> totals; "__by_number__" -> {family->{n->totals}}
    agg_shooter: Dict[str, Any] = field(default_factory=dict)

    # optional in-memory ledger (list of dicts)
    ledger: list = field(default_factory=list)

    def __post_init__(self):
        # normalize config
        self.cfg = _merge(DEFAULT_TRACKING_CFG, self.cfg or {})
        # ensure sensible types
        self.point = int(self.point or 0)

    # ---- Serialization to vs.system["tracker"] ----

    def snapshot(self) -> Dict[str, Any]:
        """Return a dict suitable for storing in VarStore.system['tracker']."""
        snap: Dict[str, Any] = {
            "roll": {
                "last_roll": self.last_roll,
                "roll_index": self.roll_index,
                "shooter_rolls": self.shooter_rolls,
                "rolls_since_point": self.rolls_since_point,
            },
            "point": {
                "point": self.point or 0,
                "point_cycle": self.point_cycle,
            },
            "bankroll": {
                "bankroll": self.bankroll,
                "bankroll_peak": self.bankroll_peak,
                "drawdown": self.drawdown,
                "max_drawdown": self.max_drawdown,
                "pnl_since_shooter": self.pnl_since_shooter,
                "pnl_since_point": self.pnl_since_point,
            },
            "hits": dict(self.hit_counts),
            "shooter": {
                "shooter_index": self.shooter_index,
                "shooter_rolls": self.shooter_rolls,
            },
            "session": {
                "shooter_count": self.shooter_count,
                "hands_played": self.hands_played,
                "seven_outs": self.seven_outs,
                "points_made": self.points_made,
            },
            "config": dict(self.cfg),
        }

        if self.cfg.get("enabled"):
            # Include aggregates if enabled
            scopes = set(self.cfg.get("scopes", ["session"]))
            include_session = "session" in scopes
            include_shooter = "shooter" in scopes
            agg_block: Dict[str, Any] = {}
            if include_session:
                agg_block["session"] = self._export_agg(self.agg_session)
            if include_shooter:
                agg_block["shooter"] = self._export_agg(self.agg_shooter)
            snap["agg"] = agg_block

            if self.cfg.get("ledger"):
                snap["ledger"] = list(self.ledger)

        return snap

    def _export_agg(self, agg: Dict[str, Any]) -> Dict[str, Any]:
        # Export totals + by_number as-is. Keep structure stable for JSON strategies.
        if not agg:
            return {}
        out = {}
        for k, v in agg.items():
            if k == "__by_number__":
                # deep copy
                fam_map = {}
                for fam, nd in v.items():
                    fam_map[fam] = {int(n): dict(t) for n, t in nd.items()}
                out["by_number"] = fam_map
            else:
                out[k] = dict(v)
        return out

    # ---- Event hooks (Phase A) ----

    def on_new_shooter(self):
        """Call when the shooter changes at table level."""
        self.shooter_count += 1
        self.shooter_index = self.shooter_count + 1  # next shooter index
        # Reset per-shooter counters:
        self.shooter_rolls = 0
        self.pnl_since_shooter = 0.0
        # point remains off until establishment
        # Do NOT reset agg_shooter here; it's reset when a shooter hand ends (seven_out/point_resolved)
        self.agg_shooter = {}  # start fresh aggregates per new shooter

    def on_roll(self, total: int):
        """Call every dice roll, provide 2..12."""
        self.last_roll = int(total)
        self.roll_index += 1
        self.shooter_rolls += 1
        if self.point:
            self.rolls_since_point += 1
        if self.cfg.get("roll_hits", True) and 2 <= total <= 12:
            self.hit_counts[total] = self.hit_counts.get(total, 0) + 1

    def on_point_established(self, p: int):
        """Call when a point is set (4/5/6/8/9/10)."""
        self.point = int(p)
        self.rolls_since_point = 0
        self.point_cycle += 1  # we started a new point cycle
        # pnl_since_point should accumulate deltas until cleared/resolved

    def on_point_made(self):
        """Call when the point is made (resolved as a win for line)."""
        self.points_made += 1
        self.point = 0
        self.rolls_since_point = 0
        self.pnl_since_point = 0.0
        if self.cfg.get("reset_shooter_on") == "point_resolved":
            self._end_shooter_hand()

    def on_seven_out(self):
        """Call when a seven-out occurs (hand ends)."""
        self.seven_outs += 1
        self.point = 0
        self.rolls_since_point = 0
        self.pnl_since_point = 0.0
        self._end_shooter_hand()

    def _end_shooter_hand(self):
        self.hands_played += 1  # completed hand
        # Start next shooter context
        self.on_new_shooter()

    def on_bankroll_delta(self, delta: float):
        """Call whenever bankroll changes (net of a roll)."""
        if not self.cfg.get("bankroll", True):
            return
        self.bankroll += float(delta)
        if self.bankroll > self.bankroll_peak:
            self.bankroll_peak = self.bankroll
        self.drawdown = max(0.0, self.bankroll_peak - self.bankroll)
        if self.drawdown > self.max_drawdown:
            self.max_drawdown = self.drawdown

        # contextual PnL
        self.pnl_since_shooter += float(delta)
        if self.point:
            self.pnl_since_point += float(delta)

    def on_point_cleared(self):
        """Call when point turns off with no explicit 'made' (e.g., already handled)."""
        self.point = 0
        self.rolls_since_point = 0
        self.pnl_since_point = 0.0

    # ---- Aggregates (Phase B) ----

    def record_resolution(
        self,
        *,
        family: str,
        result: str,  # "win" | "lose" | "push"
        number: Optional[int] = None,   # e.g., 4/5/6/8/9/10 for place/buy/lay/hardways; None for line/center bets
        flat_delta: float = 0.0,        # net paid/collected on flat
        odds_delta: float = 0.0,        # net paid/collected on odds (positive for win, negative for loss)
        stake_flat: float = 0.0,        # optional: at-risk flat amount (for ROI-like metrics later)
        stake_odds: float = 0.0,        # optional: at-risk odds amount
        extra: Optional[Dict[str, Any]] = None,  # optional structured metadata
    ):
        """Aggregate a resolved bet result into shooter/session scopes."""
        if not self.cfg.get("enabled"):
            return
        if not self.cfg.get("families", {}).get(family, True):
            return

        odds_breakout = bool(self.cfg.get("odds_breakout", True))
        by_num = bool(self.cfg.get("by_number", True))
        num = int(number) if number is not None else None

        # Prepare delta/stake normalized
        fdelta = float(flat_delta or 0.0)
        odelta = float(odds_delta or 0.0)
        net = fdelta + odelta
        stake = float(stake_flat or 0.0) + float(stake_odds or 0.0)

        # Update both session & shooter scopes (if configured)
        scopes = set(self.cfg.get("scopes", ["session"]))
        if "session" in scopes:
            self._apply_to_agg(self.agg_session, family, num if by_num else None, result, fdelta, odelta, net, stake, odds_breakout)
        if "shooter" in scopes:
            self._apply_to_agg(self.agg_shooter, family, num if by_num else None, result, fdelta, odelta, net, stake, odds_breakout)

        # Optional in-memory ledger entry
        if self.cfg.get("ledger"):
            self.ledger.append({
                "family": family,
                "number": num,
                "result": result,
                "flat_delta": fdelta,
                "odds_delta": odelta,
                "net": net,
                "stake_flat": float(stake_flat or 0.0),
                "stake_odds": float(stake_odds or 0.0),
                "roll_index": self.roll_index,
                "shooter_index": self.shooter_index,
                "point": self.point or 0,
                "extra": extra or {},
            })

    def _apply_to_agg(
        self,
        agg: Dict[str, Any],
        family: str,
        number: Optional[int],
        result: str,
        fdelta: float,
        odelta: float,
        net: float,
        stake: float,
        odds_breakout: bool,
    ):
        fam_tot, num_tot = _agg_for(agg, family, number, odds_breakout)

        def _bump(tot: Dict[str, Any]):
            tot["bets"] += 1
            if result == "win":
                tot["wins"] += 1
            elif result == "lose":
                tot["losses"] += 1
            else:
                tot["pushes"] += 1
            tot["flat_delta"] += fdelta
            tot["odds_delta"] += odelta
            tot["net"] += net
            tot["stake"] += stake

        _bump(fam_tot)
        if num_tot is not None:
            _bump(num_tot)