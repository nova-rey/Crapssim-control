"""
Module CLI for batch execution without altering the primary CLI.

Usage:
  python -m csc.cli_batch --plan path/to/plan.yaml
"""

import argparse
from .batch_runner import run_batch


def main():
    ap = argparse.ArgumentParser(prog="csc-batch", description="CSC batch runner")
    ap.add_argument("--plan", required=True, help="Path to batch plan (YAML or JSON)")
    args = ap.parse_args()
    run_batch(args.plan)


if __name__ == "__main__":
    main()
