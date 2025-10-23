"""
CLI wrapper for sweep + aggregate.

Usage:
  python -m csc.cli_sweep --plan examples/sweep_grid.yaml --metric ROI --top 10 --compare
"""
import argparse
import os
from .sweep import run_sweep, expand_plan
from .aggregator import aggregate


def main():
    ap = argparse.ArgumentParser(prog="csc-sweep", description="CSC sweep runner + aggregator")
    ap.add_argument("--plan", required=True, help="Path to sweep plan (YAML or JSON)")
    ap.add_argument("--metric", default="ROI", help="Leaderboard metric (e.g., ROI, bankroll_final, hands, rolls)")
    ap.add_argument("--top", type=int, default=10, help="Leaderboard size")
    ap.add_argument("--compare", action="store_true", help="Write comparisons.json with deltas and correlations")
    args = ap.parse_args()

    # Expand once to learn out_dir
    _, out_dir, _ = expand_plan(args.plan)
    manifest_path = run_sweep(args.plan)
    out = aggregate(out_dir=out_dir, leaderboard_metric=args.metric, top_k=args.top, write_comparisons=args.compare)
    print(f"Sweep complete. Manifest: {manifest_path}. Leaderboard: {out['leaderboard_path']}.")
    if args.compare and out.get("comparisons_path"):
        print(f"Comparisons: {out['comparisons_path']}")


if __name__ == "__main__":
    main()
