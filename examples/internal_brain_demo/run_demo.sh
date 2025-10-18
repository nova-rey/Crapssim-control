#!/usr/bin/env bash
# Phase 5 Internal Brain Integration Demo
set -e

echo "Running CSC Internal Brain demo..."
python -m crapssim_control.cli run \
  examples/internal_brain_demo/spec.yaml \
  --export baselines/phase5/summary.csv \
  --seed 12345

python examples/internal_brain_demo/generate_baseline.py

echo "Integration run complete. Artifacts available in baselines/phase5/"
