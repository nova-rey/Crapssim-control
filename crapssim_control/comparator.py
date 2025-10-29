from __future__ import annotations
import math
from typing import Any, Dict, List, Optional, Tuple

Numeric = (int, float)


def _is_num(x: Any) -> bool:
    return isinstance(x, Numeric) and not (isinstance(x, float) and math.isnan(x))


def make_leaderboard(
    rows: List[Dict[str, Any]], metric: str, top_k: int = 10
) -> List[Dict[str, Any]]:
    """
    Returns a new list sorted by `metric` desc (missing -> bottom).
    Deterministic tie-breaker: run_id ascending.
    """
    filtered = [r for r in rows if _is_num(r.get(metric))]
    # Stable tiebreak by run_id
    filtered.sort(key=lambda r: (-(r[metric]), r.get("run_id", "")))
    return filtered[:top_k]


def _delta(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if _is_num(a) and _is_num(b):
        return a - b
    return None


def _ratio(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if _is_num(a) and _is_num(b) and b != 0:
        return a / b
    return None


def make_comparisons(rows: List[Dict[str, Any]], metric: str) -> Dict[str, Any]:
    """
    Build delta set vs. the top row (by metric). Skips rows without numeric metric.
    """
    numeric = [r for r in rows if _is_num(r.get(metric))]
    if not numeric:
        return {"metric": metric, "top_run": None, "comparisons": [], "correlations": {}}
    top = sorted(numeric, key=lambda r: (-(r[metric]), r.get("run_id", "")))[0]
    comps: List[Dict[str, Any]] = []
    for r in numeric:
        if r is top:
            continue
        comps.append(
            {
                "run_id": r.get("run_id"),
                f"delta_{metric}": _delta(r.get(metric), top.get(metric)),
                "delta_bankroll_final": _delta(r.get("bankroll_final"), top.get("bankroll_final")),
                "delta_max_drawdown": _delta(r.get("max_drawdown"), top.get("max_drawdown")),
                "relative_efficiency": _ratio(r.get(metric), top.get(metric)),
            }
        )
    return {
        "metric": metric,
        "top_run": top.get("run_id"),
        "comparisons": comps,
        "correlations": _correlations(rows),
    }


def _pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def _collect(rows: List[Dict[str, Any]], a: str, b: str) -> Tuple[List[float], List[float]]:
    xs: List[float] = []
    ys: List[float] = []
    for r in rows:
        va, vb = r.get(a), r.get(b)
        if _is_num(va) and _is_num(vb):
            xs.append(float(va))
            ys.append(float(vb))
    return xs, ys


def _correlations(rows: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    pairs = [("ROI", "max_drawdown"), ("ROI", "hands"), ("ROI", "rolls")]
    out: Dict[str, Optional[float]] = {}
    for a, b in pairs:
        xs, ys = _collect(rows, a, b)
        out[f"{a}~{b}"] = _pearson(xs, ys)
    return out
