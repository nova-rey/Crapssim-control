from __future__ import annotations
import csv
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

Number = float

# -------------------------------
# Data model expected from journal
# -------------------------------
# Minimal columns used (others ignored if present):
# - roll_index: int            # 0-based index of the roll across the run
# - hand_id: int               # integer hand id
# - roll_in_hand: int          # 1-based index inside the hand
# - point_on: int              # 0/1 at the time of roll
# - bankroll_after: float      # bankroll immediately after this roll settles
# - hand_result: str           # "win" | "loss" | "push" (present on final roll of a hand; empty otherwise)
# - point_state: str           # "off" | "established" | "made" | "seven_out" (emitted on final roll of a hand or on transitions)
# - established_flag: int      # 1 on the roll that established a point, else 0
# - made_flag: int             # 1 on the roll that made the point, else 0
# - seven_out_flag: int        # 1 on the roll that sevened out while point was on, else 0
#
# Bet family digest input (optional; aggregator can skip): a list of dicts
#   [{"name": "pass_line", "net": 85, "wagered": 640, "wins": 22, "losses": 18}, ...]

@dataclass
class RollRow:
    roll_index: int
    hand_id: int
    roll_in_hand: int
    point_on: bool
    bankroll_after: Number
    hand_result: Optional[str]  # "win"|"loss"|"push"|None
    point_state: Optional[str]  # "off"|"established"|"made"|"seven_out"|None
    established_flag: int
    made_flag: int
    seven_out_flag: int


def _to_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _to_float(x: Any, default: float = math.nan) -> float:
    try:
        return float(x)
    except Exception:
        return default


def parse_journal_csv(path: str) -> List[RollRow]:
    rows: List[RollRow] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(
                RollRow(
                    roll_index=_to_int(r.get("roll_index", len(rows))),
                    hand_id=_to_int(r.get("hand_id", 0)),
                    roll_in_hand=_to_int(r.get("roll_in_hand", 1)),
                    point_on=bool(_to_int(r.get("point_on", 0))),
                    bankroll_after=_to_float(r.get("bankroll_after", "nan")),
                    hand_result=(r.get("hand_result") or None),
                    point_state=(r.get("point_state") or None),
                    established_flag=_to_int(r.get("established_flag", 0)),
                    made_flag=_to_int(r.get("made_flag", 0)),
                    seven_out_flag=_to_int(r.get("seven_out_flag", 0)),
                )
            )
    return rows


# -------------------------------
# Metric computations (pure)
# -------------------------------

def compute_bankroll_series(rows: List[RollRow]) -> Tuple[Optional[float], Optional[float], Optional[int], Optional[int], Optional[float], Optional[float]]:
    """Return (start, final, peak_idx, trough_idx, max_dd_abs, max_dd_pct)."""
    if not rows:
        return None, None, None, None, None, None
    series = [r.bankroll_after for r in rows if not math.isnan(r.bankroll_after)]
    if not series:
        return None, None, None, None, None, None
    start = series[0]
    final = series[-1]
    peak = series[0]
    peak_idx = 0
    trough_idx = 0
    max_dd_abs = 0.0
    max_dd_pct = 0.0
    for i, val in enumerate(series):
        if val > peak:
            peak = val
            peak_idx = i
        drawdown = peak - val
        if drawdown > max_dd_abs:
            max_dd_abs = drawdown
            trough_idx = i
            if peak > 0:
                max_dd_pct = drawdown / peak
    return start, final, peak_idx, trough_idx, max_dd_abs, max_dd_pct


def compute_point_cycle(rows: List[RollRow]) -> Dict[str, Any]:
    established = sum(1 for r in rows if r.established_flag == 1)
    made = sum(1 for r in rows if r.made_flag == 1)
    seven_outs = sum(1 for r in rows if r.seven_out_flag == 1)
    # PSO: establish then immediate 7-out (roll_in_hand == 2 and seven_out_flag==1)
    # If journal marks flags, we can derive PSO robustly:
    pso_count = 0
    # Count by hand: first made_flag/ seven_out_flag after establishment
    per_hand_rolls: Dict[int, List[RollRow]] = {}
    for r in rows:
        per_hand_rolls.setdefault(r.hand_id, []).append(r)
    for hid, hrows in per_hand_rolls.items():
        hrows_sorted = sorted(hrows, key=lambda x: x.roll_in_hand)
        est_idx = next((i for i, x in enumerate(hrows_sorted) if x.established_flag == 1), None)
        if est_idx is not None and est_idx + 1 < len(hrows_sorted):
            # PSO if very next roll is seven_out
            if hrows_sorted[est_idx + 1].seven_out_flag == 1:
                pso_count += 1
    avg_rolls_per_hand = None
    if per_hand_rolls:
        avg_rolls_per_hand = sum(len(v) for v in per_hand_rolls.values()) / len(per_hand_rolls)
    return {
        "established": established,
        "made": made,
        "seven_outs": seven_outs,
        "pso_count": pso_count,
        "pso_rate": (pso_count / established) if established else 0.0,
        "avg_rolls_per_hand": avg_rolls_per_hand,
    }


def compute_streaks(rows: List[RollRow]) -> Tuple[int, int]:
    # Evaluate on final roll of each hand only (hand_result present)
    win_streak = 0
    loss_streak = 0
    win_max = 0
    loss_max = 0
    last_hand_seen = None
    for r in rows:
        if r.hand_result and (last_hand_seen is None or r.hand_id != last_hand_seen):
            last_hand_seen = r.hand_id
            if r.hand_result == "win":
                win_streak += 1
                loss_streak = 0
            elif r.hand_result == "loss":
                loss_streak += 1
                win_streak = 0
            else:
                # push breaks both
                win_streak = 0
                loss_streak = 0
            win_max = max(win_max, win_streak)
            loss_max = max(loss_max, loss_streak)
    return win_max, loss_max


def compute_point_on_pct(rows: List[RollRow]) -> Optional[float]:
    if not rows:
        return None
    on = sum(1 for r in rows if r.point_on)
    return on / len(rows) if rows else None


def digest_by_bet_family(digest_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Expect rows with keys: name, net, wagered, wins, losses
    if not digest_rows:
        return {"digest": [], "top_name": None, "top_net": None}
    ordered = sorted(digest_rows, key=lambda d: float(d.get("net", 0.0)), reverse=True)
    top = ordered[0]
    return {"digest": ordered, "top_name": top.get("name"), "top_net": top.get("net")}


def compute_report_v2(
    rows: List[RollRow],
    bankroll_start: Optional[float],
    bet_family_digest: Optional[List[Dict[str, Any]]] = None,
    identity_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    start, final, peak_idx, trough_idx, max_dd_abs, max_dd_pct = compute_bankroll_series(rows)
    if bankroll_start is None:
        bankroll_start = start
    roi = None
    if bankroll_start not in (None, 0) and final is not None:
        roi = (final - bankroll_start) / bankroll_start
    point_cycle = compute_point_cycle(rows)
    win_max, loss_max = compute_streaks(rows)
    point_on_pct = compute_point_on_pct(rows)
    by_bet = digest_by_bet_family(bet_family_digest or [])

    report = {
        "identity": {
            "journal_schema_version": "1.2",
            "summary_schema_version": "1.2",
            "report_schema_version": "2.0",
        },
        "summary": {
            "bankroll_start": bankroll_start,
            "bankroll_final": final,
            "roi": roi,
            "hands_played": len({r.hand_id for r in rows}) if rows else 0,
            "rolls": len(rows),
            "pso_count": point_cycle["pso_count"],
            "points_made": point_cycle["made"],
            "max_drawdown": max_dd_abs,
            "max_drawdown_pct": max_dd_pct,
            "win_streak_max": win_max,
            "loss_streak_max": loss_max,
            "point_on_time_pct": point_on_pct,
        },
        "point_cycle": {
            "established": point_cycle["established"],
            "made": point_cycle["made"],
            "seven_outs": point_cycle["seven_outs"],
            "pso_rate": point_cycle["pso_rate"],
            "avg_rolls_per_hand": point_cycle["avg_rolls_per_hand"],
        },
        "risk_series": {
            "peak_bankroll": None,  # optional if you track running peak $ explicitly
            "trough_bankroll": None,
            "peak_index": peak_idx,
            "trough_index": trough_idx,
        },
        "by_bet_family": by_bet,
        "flags": {
            "strict": False,
            "demo_fallbacks": False,
        },
    }
    if identity_overrides:
        report["identity"].update(identity_overrides)
    return report
