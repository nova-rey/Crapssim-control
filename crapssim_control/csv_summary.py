from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from datetime import datetime


# ----------------------------- helpers --------------------------------------- #

def _to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if s == "":
        return None
    try:
        return float(s)
    except Exception:
        return None


def _to_int(x: Any) -> Optional[int]:
    if x is None:
        return None
    try:
        return int(float(x))  # tolerate "6.0"
    except Exception:
        return None


def _parse_ts(s: Any) -> Optional[datetime]:
    if s is None:
        return None
    txt = str(s).strip()
    if not txt:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(txt, fmt)
        except Exception:
            pass
    return None


def _first_last(ts_iter: Iterable[Optional[datetime]]) -> Tuple[Optional[str], Optional[str]]:
    vals = [t for t in ts_iter if t is not None]
    if not vals:
        return None, None
    vals.sort()
    def fmt(t: datetime) -> str:
        return t.strftime("%Y-%m-%dT%H:%M:%S")
    return fmt(vals[0]), fmt(vals[-1])


def _default_group_key_for_file(journal_path: Path) -> str:
    return f"file:{journal_path.name}"


# ----------------------------- core API -------------------------------------- #

def summarize_journal(
    journal_path: str | Path,
    *,
    group_by_run_id: bool = True,
) -> List[Dict[str, Any]]:
    """
    Read a per-event action journal CSV and return one or more summary rows.

    When group_by_run_id=True and the file contains a 'run_id' column,
    rows are grouped per run_id; otherwise a single summary for the file
    is returned.

    Returned dict columns (when available):
      - run_id
      - rows_total
      - actions_total
      - sets, clears, presses, reduces, switch_mode
      - unique_bets
      - modes_used
      - points_seen
      - roll_events   (distinct roll ticks by timestamp)
      - regress_events
      - sum_amount_set, sum_amount_press, sum_amount_reduce
      - first_timestamp, last_timestamp
      - path
    """
    p = Path(journal_path)
    try:
        with p.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception:
        return []

    if not rows:
        return [{
            "run_id": _default_group_key_for_file(p),
            "rows_total": 0,
            "actions_total": 0,
            "sets": 0,
            "clears": 0,
            "presses": 0,
            "reduces": 0,
            "switch_mode": 0,
            "unique_bets": 0,
            "modes_used": 0,
            "points_seen": 0,
            "roll_events": 0,
            "regress_events": 0,
            "sum_amount_set": 0.0,
            "sum_amount_press": 0.0,
            "sum_amount_reduce": 0.0,
            "first_timestamp": None,
            "last_timestamp": None,
            "path": str(p),
        }]

    has_run_id_col = "run_id" in rows[0]
    groups: Dict[str, List[Dict[str, Any]]] = {}

    if group_by_run_id and has_run_id_col:
        for r in rows:
            key = (r.get("run_id") or "").strip()
            if not key:
                key = _default_group_key_for_file(p)
            groups.setdefault(key, []).append(r)
    else:
        groups[_default_group_key_for_file(p)] = rows

    summaries: List[Dict[str, Any]] = []

    for key, grp in groups.items():
        bet_types = set()
        modes = set()
        points = set()

        rows_total = 0
        sets = clears = presses = reduces = switch_mode = 0
        regress_events = 0

        sum_amount_set = 0.0
        sum_amount_press = 0.0
        sum_amount_reduce = 0.0

        ts_list: List[Optional[datetime]] = []

        # Distinct roll “ticks” by timestamp (fallback to row idx)
        roll_ticks: set[Tuple[str, str]] = set()

        for idx, r in enumerate(grp):
            rows_total += 1

            evt = (r.get("event_type") or "").strip().lower()
            ts_str = (r.get("timestamp") or "").strip()
            if evt == "roll":
                key_ts = ts_str if ts_str else f"__row_{idx}"
                roll_ticks.add((evt, key_ts))

            act = (r.get("action") or "").strip().lower()
            if act == "set":
                sets += 1
            elif act == "clear":
                clears += 1
            elif act == "press":
                presses += 1
            elif act == "reduce":
                reduces += 1
            elif act == "switch_mode":
                switch_mode += 1

            bt = (r.get("bet_type") or "").strip()
            if bt:
                bet_types.add(bt)

            m = (r.get("mode") or "").strip()
            if m:
                modes.add(m)

            pt = _to_int(r.get("point"))
            if pt and pt != 0:
                points.add(pt)

            rid = (r.get("id") or "").strip()
            if act == "clear" and rid == "template:regress_roll3":
                regress_events += 1

            amt = _to_float(r.get("amount"))
            if amt is not None:
                if act == "set":
                    sum_amount_set += amt
                elif act == "press":
                    sum_amount_press += amt
                elif act == "reduce":
                    sum_amount_reduce += amt

            ts = _parse_ts(ts_str)
            ts_list.append(ts)

        first_ts, last_ts = _first_last(ts_list)

        summaries.append({
            "run_id": key,
            "rows_total": rows_total,
            "actions_total": rows_total,  # one row per action in the journal
            "sets": sets,
            "clears": clears,
            "presses": presses,
            "reduces": reduces,
            "switch_mode": switch_mode,
            "unique_bets": len(bet_types),
            "modes_used": len(modes),
            "points_seen": len(points),
            "roll_events": len(roll_ticks),  # distinct roll timestamps
            "regress_events": regress_events,
            "sum_amount_set": round(sum_amount_set, 4),
            "sum_amount_press": round(sum_amount_press, 4),
            "sum_amount_reduce": round(sum_amount_reduce, 4),
            "first_timestamp": first_ts,
            "last_timestamp": last_ts,
            "path": str(p),
        })

    return summaries


def write_summary_csv(
    summaries: List[Dict[str, Any]],
    out_path: str | Path,
    *,
    append: bool = False,
) -> None:
    """
    Write a list of summary dicts to CSV. Creates parent dirs if needed.
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "run_id",
        "rows_total",
        "actions_total",
        "sets",
        "clears",
        "presses",
        "reduces",
        "switch_mode",
        "unique_bets",
        "modes_used",
        "points_seen",
        "roll_events",
        "regress_events",
        "sum_amount_set",
        "sum_amount_press",
        "sum_amount_reduce",
        "first_timestamp",
        "last_timestamp",
        "path",
    ]

    write_header = True
    if append and out.exists():
        try:
            write_header = out.stat().st_size == 0
        except Exception:
            write_header = False

    mode = "a" if append else "w"
    with out.open(mode, encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if (not append) or write_header:
            writer.writeheader()
        for row in summaries:
            safe = {k: row.get(k, "") for k in fieldnames}
            writer.writerow(safe)