import csv
import json
import os
import statistics
import zipfile
from typing import Any, Dict, List, Optional

from .comparator import make_comparisons, make_leaderboard


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_report_from_artifacts_dir(artifacts_dir: str) -> Optional[Dict[str, Any]]:
    rp = os.path.join(artifacts_dir, "report.json")
    if os.path.isfile(rp):
        return _load_json(rp)
    return None


def _read_report_from_zip(output_zip: str) -> Optional[Dict[str, Any]]:
    if not (output_zip and os.path.isfile(output_zip)):
        return None
    try:
        with zipfile.ZipFile(output_zip, "r") as z:
            # default location from C1: artifacts/report.json
            target = "artifacts/report.json"
            if target in z.namelist():
                with z.open(target, "r") as f:
                    return json.loads(f.read().decode("utf-8"))
    except Exception:
        return None
    return None


def _get_metric(report: Dict[str, Any], keys: List[str], default=None):
    cur: Any = report
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _compute_roi(final_bankroll: Optional[float], start_bankroll: Optional[float]) -> Optional[float]:
    if final_bankroll is None or start_bankroll is None:
        return None
    try:
        if start_bankroll == 0:
            return None
        return (final_bankroll - start_bankroll) / start_bankroll
    except Exception:
        return None


def _summarize_rows(rows: List[Dict[str, Any]], metric: str, top_k: int = 10) -> Dict[str, Any]:
    vals = [r[metric] for r in rows if isinstance(r.get(metric), (int, float))]
    agg: Dict[str, Any] = {
        "count": len(vals),
        "mean": statistics.mean(vals) if vals else None,
        "median": statistics.median(vals) if vals else None,
        "stdev": statistics.stdev(vals) if len(vals) > 1 else 0 if len(vals) == 1 else None,
        "min": min(vals) if vals else None,
        "max": max(vals) if vals else None,
    }
    top = sorted([r for r in rows if isinstance(r.get(metric), (int, float))], key=lambda r: r[metric], reverse=True)[:top_k]
    agg["top_k"] = [{"run_id": r["run_id"], metric: r[metric]} for r in top]
    return agg


def aggregate(out_dir: str, leaderboard_metric: str = "ROI", top_k: int = 10, write_comparisons: bool = False) -> Dict[str, Any]:
    manifest_path = os.path.join(out_dir, "batch_manifest.json")
    batch_manifest = _load_json(manifest_path)

    rows: List[Dict[str, Any]] = []
    for rec in batch_manifest.get("items", []):
        row: Dict[str, Any] = {
            "run_id": rec.get("run_id"),
            "source": rec.get("source"),
            "input_type": rec.get("input_type"),
            "status": rec.get("status"),
            "bankroll_final": None,
            "ROI": None,
            "hands": None,
            "rolls": None,
            "max_drawdown": None,
            "pso_count": None,
            "points_made": None,
            "top_bet_family": None,
            "artifacts_dir": rec.get("artifacts_dir"),
            "artifacts_zip": rec.get("output_zip"),
            "error": rec.get("error"),
        }

        report = None
        if rec.get("status") == "success":
            # Prefer artifacts_dir/report.json; fallback to output_zip/artifacts/report.json
            if rec.get("artifacts_dir") and os.path.isdir(rec["artifacts_dir"]):
                report = _read_report_from_artifacts_dir(rec["artifacts_dir"])
            if report is None and rec.get("output_zip"):
                report = _read_report_from_zip(rec["output_zip"])

        if report:
            # Expect stable fields; tolerate missing values
            final = _get_metric(report, ["summary", "bankroll_final"])
            start = _get_metric(report, ["summary", "bankroll_start"])
            row["bankroll_final"] = final
            row["ROI"] = _compute_roi(final, start)
            row["hands"] = _get_metric(report, ["summary", "hands_played"])
            row["rolls"] = _get_metric(report, ["summary", "rolls"])
            row["max_drawdown"] = _get_metric(report, ["summary", "max_drawdown"])
            row["pso_count"] = _get_metric(report, ["summary", "pso_count"])
            row["points_made"] = _get_metric(report, ["summary", "points_made"])
            row["top_bet_family"] = _get_metric(report, ["by_bet_family", "top_name"])
        else:
            if not row.get("error"):
                row["error"] = "report_not_found"

        rows.append(row)

    # Write batch_index.json
    index_path = os.path.join(out_dir, "batch_index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, sort_keys=True)

    # Write batch_index.csv
    csv_path = os.path.join(out_dir, "batch_index.csv")
    fieldnames = [
        "run_id","source","input_type","status",
        "bankroll_final","ROI","hands","rolls","max_drawdown",
        "pso_count","points_made","top_bet_family",
        "artifacts_dir","artifacts_zip","error"
    ]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fieldnames})

    # Aggregates & leaderboard
    aggregates: Dict[str, Any] = {
        "total_runs": len(rows),
        "successes": sum(1 for r in rows if r.get("status") == "success"),
        "errors": sum(1 for r in rows if r.get("status") != "success"),
        "metrics": {
            "ROI": _summarize_rows(rows, "ROI", top_k=top_k),
            "bankroll_final": _summarize_rows(rows, "bankroll_final", top_k=top_k),
            "hands": _summarize_rows(rows, "hands", top_k=top_k),
            "rolls": _summarize_rows(rows, "rolls", top_k=top_k),
        },
    }
    aggregates_path = os.path.join(out_dir, "aggregates.json")
    with open(aggregates_path, "w", encoding="utf-8") as f:
        json.dump(aggregates, f, indent=2, sort_keys=True)

    # Leaderboard (by chosen metric)
    leaderboard = make_leaderboard(rows, leaderboard_metric, top_k=top_k)
    leaderboard_path = os.path.join(out_dir, "leaderboard.json")
    with open(leaderboard_path, "w", encoding="utf-8") as f:
        json.dump(leaderboard, f, indent=2, sort_keys=True)

    leaderboard_csv_path = os.path.join(out_dir, "leaderboard.csv")
    lb_fields = [
        "run_id",
        leaderboard_metric,
        "bankroll_final",
        "hands",
        "rolls",
        "max_drawdown",
        "pso_count",
        "points_made",
        "top_bet_family",
    ]
    with open(leaderboard_csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=lb_fields)
        w.writeheader()
        for r in leaderboard:
            out_row = {k: r.get(k) for k in lb_fields}
            out_row[leaderboard_metric] = r.get(leaderboard_metric)
            w.writerow(out_row)

    comparisons_path = None
    if write_comparisons:
        comps = make_comparisons(rows, leaderboard_metric)
        comparisons_path = os.path.join(out_dir, "comparisons.json")
        with open(comparisons_path, "w", encoding="utf-8") as f:
            json.dump(comps, f, indent=2, sort_keys=True)

    return {
        "index_path": index_path,
        "csv_path": csv_path,
        "aggregates_path": aggregates_path,
        "leaderboard_path": leaderboard_path,
        "leaderboard_csv_path": leaderboard_csv_path,
        "comparisons_path": comparisons_path,
        "rows": len(rows),
    }
