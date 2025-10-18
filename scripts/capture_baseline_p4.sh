#!/usr/bin/env bash
set -euo pipefail

OUTDIR="baselines/phase4"
SEED_SPEC="examples/quickstart_spec.json"
SEED="12345"

mkdir -p "$OUTDIR"

echo "Running seeded Phase 4 baseline..."
python -m crapssim_control.cli run "$SEED_SPEC" \
  --export \
  --strict \
  --demo-fallbacks \
  --webhook-url http://localhost:1880/hook \
  --webhook-timeout 2.0 \
  --evo-enabled \
  --trial-tag baseline_p4 \
  --seed "$SEED"

cp -f export/journal.csv   "$OUTDIR/journal.csv"
cp -f export/report.json   "$OUTDIR/report.json"
cp -f export/manifest.json "$OUTDIR/manifest.json"

echo "Baseline captured in $OUTDIR"
