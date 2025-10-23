"""
CLI wrapper for sweep + aggregate.

Usage:
  python -m csc.cli_sweep --plan examples/sweep_grid.yaml
"""
import argparse
import os
from .sweep import run_sweep, expand_plan
from .aggregator import aggregate


def main():
    ap = argparse.ArgumentParser(prog="csc-sweep", description="CSC sweep runner + aggregator")
    ap.add_argument("--plan", required=True, help="Path to sweep plan (YAML or JSON)")
    ap.add_argument("--top-k", type=int, default=10, help="Leaderboard size")
    args = ap.parse_args()

    # Expand once to learn out_dir
    _, out_dir, _ = expand_plan(args.plan)
    manifest_path = run_sweep(args.plan)
    _ = aggregate(out_dir=out_dir, top_k=args.top_k)
    print(f"Sweep complete. Manifest: {manifest_path}. Outputs written under: {out_dir}")


if __name__ == "__main__":
    main()
