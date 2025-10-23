"""Capture a small, deterministic Phase 13 baseline:
- Expands & runs a sweep plan via csc.sweep / csc.aggregator
- Copies core outputs into baselines/phase13/
- Writes a baseline manifest w/ schema versions and quick stats
- Emits a TAG file (for CI to convert to a git tag)

Usage:
  python tools/capture_phase13_baseline.py --plan examples/baseline_sweep.yaml --tag v0.43.0-phase13-baseline --compare
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
from datetime import datetime
from typing import Any

from csc.sweep import expand_plan, run_sweep
from csc.aggregator import aggregate

def _load_json(p: str):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def _dump_json(p: str, obj: Any):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)

def _copy_if_exists(src: str, dst: str):
    if os.path.isfile(src):
        shutil.copy2(src, dst)

def main():
    ap = argparse.ArgumentParser(description="Capture Phase 13 baseline")
    ap.add_argument("--plan", required=True, help="Sweep plan file (YAML or JSON)")
    ap.add_argument("--tag", required=True, help="Version tag string, e.g., v0.43.0-phase13-baseline")
    ap.add_argument("--compare", action="store_true", help="Write comparisons.json via aggregator")
    args = ap.parse_args()

    # 1) Run sweep → batch + aggregate
    _, out_dir, _ = expand_plan(args.plan)
    run_sweep(args.plan)
    aggregate(out_dir=out_dir, leaderboard_metric="ROI", top_k=10, write_comparisons=args.compare)

    # 2) Prepare baseline dir
    base_dir = os.path.join("baselines", "phase13")
    os.makedirs(base_dir, exist_ok=True)

    # 3) Copy core batch artifacts
    _copy_if_exists(os.path.join(out_dir, "batch_manifest.json"), os.path.join(base_dir, "batch_manifest.json"))
    _copy_if_exists(os.path.join(out_dir, "batch_index.json"),   os.path.join(base_dir, "batch_index.json"))
    _copy_if_exists(os.path.join(out_dir, "batch_index.csv"),    os.path.join(base_dir, "batch_index.csv"))
    _copy_if_exists(os.path.join(out_dir, "aggregates.json"),    os.path.join(base_dir, "aggregates.json"))
    _copy_if_exists(os.path.join(out_dir, "leaderboard.json"),   os.path.join(base_dir, "leaderboard.json"))
    _copy_if_exists(os.path.join(out_dir, "leaderboard.csv"),    os.path.join(base_dir, "leaderboard.csv"))
    if args.compare:
        _copy_if_exists(os.path.join(out_dir, "comparisons.json"), os.path.join(base_dir, "comparisons.json"))

    # 4) Copy a few sample per-run reports (if present)
    samples_dir = os.path.join(base_dir, "sample_reports")
    os.makedirs(samples_dir, exist_ok=True)
    index = _load_json(os.path.join(out_dir, "batch_index.json"))
    copied = 0
    for row in index:
        if row.get("status") != "success":
            continue
        # Prefer artifacts_dir/report.json; fallback to output_zip/artifacts/report.json is already in aggregator
        ad = row.get("artifacts_dir")
        if ad and os.path.isfile(os.path.join(ad, "report.json")):
            dst = os.path.join(samples_dir, f"{row['run_id']}_report.json")
            _copy_if_exists(os.path.join(ad, "report.json"), dst)
            copied += 1
        if copied >= 5:
            break

    # 5) Write baseline manifest w/ quick stats
    aggregates = _load_json(os.path.join(base_dir, "aggregates.json"))
    metrics = aggregates.get("metrics", {})
    baseline_manifest = {
        "tag": args.tag,
        "captured_at": datetime.utcnow().isoformat() + "Z",
        "schema": {
            "journal": "1.2",
            "summary": "1.2",
            "report": "2.0"
        },
        "runs": {
            "total": aggregates.get("total_runs"),
            "successes": aggregates.get("successes"),
            "errors": aggregates.get("errors"),
        },
        "roi": {
            "mean": (metrics.get("ROI") or {}).get("mean"),
            "min": (metrics.get("ROI") or {}).get("min"),
            "max": (metrics.get("ROI") or {}).get("max")
        }
    }
    _dump_json(os.path.join(base_dir, "baseline_manifest.json"), baseline_manifest)

    # 6) Emit TAG file (for CI to create git tag)
    with open(os.path.join(base_dir, "TAG"), "w", encoding="utf-8") as f:
        f.write(args.tag + "\n")

    print(f"Baseline captured to {base_dir}")
    print(f"Suggested tag: {args.tag}")

if __name__ == "__main__":
    main()
