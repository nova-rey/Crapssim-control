from __future__ import annotations
import csv
import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .schemas import JOURNAL_SCHEMA_VERSION, SUMMARY_SCHEMA_VERSION

Number = float

# Minimal journal columns consumed:
# roll_index, hand_id, roll_in_hand, point_on, bankroll_after,
# hand_result, point_state, established_flag, made_flag, seven_out_flag


@dataclass
class RollRow:
    roll_index: int
    hand_id: int
    roll_in_hand: int
    point_on: bool
    bankroll_after: Number
    hand_result: Optional[str]
    point_state: Optional[str]
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


def compute_bankroll_series(
    rows: List[RollRow],
) -> Tuple[
    Optional[float], Optional[float], Optional[int], Optional[int], Optional[float], Optional[float]
]:
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
    pso_count = 0
    per_hand: Dict[int, List[RollRow]] = {}
    for r in rows:
        per_hand.setdefault(r.hand_id, []).append(r)
    for hid, hrows in per_hand.items():
        hrows_sorted = sorted(hrows, key=lambda x: x.roll_in_hand)
        est_idx = next((i for i, x in enumerate(hrows_sorted) if x.established_flag == 1), None)
        if est_idx is not None and est_idx + 1 < len(hrows_sorted):
            if hrows_sorted[est_idx + 1].seven_out_flag == 1:
                pso_count += 1
    avg_rolls_per_hand = None
    if per_hand:
        avg_rolls_per_hand = sum(len(v) for v in per_hand.values()) / len(per_hand)
    return {
        "established": established,
        "made": made,
        "seven_outs": seven_outs,
        "pso_count": pso_count,
        "pso_rate": (pso_count / established) if established else 0.0,
        "avg_rolls_per_hand": avg_rolls_per_hand,
    }


def compute_streaks(rows: List[RollRow]) -> Tuple[int, int]:
    win_streak = 0
    loss_streak = 0
    win_max = 0
    loss_max = 0
    seen_hand = set()
    for r in rows:
        if r.hand_result and r.hand_id not in seen_hand:
            seen_hand.add(r.hand_id)
            if r.hand_result == "win":
                win_streak += 1
                loss_streak = 0
            elif r.hand_result == "loss":
                loss_streak += 1
                win_streak = 0
            else:
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
            "journal_schema_version": JOURNAL_SCHEMA_VERSION,
            "summary_schema_version": SUMMARY_SCHEMA_VERSION,
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
            "peak_bankroll": None,
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
