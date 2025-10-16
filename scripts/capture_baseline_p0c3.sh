#!/usr/bin/env bash
set -euo pipefail

# capture_baseline_p0c3.sh
# Phase 0 · Checkpoint 3 (Hygiene): produce deterministic baseline artifacts.
# Outputs:
#   baselines/p0c3/journal.csv
#   baselines/p0c3/report.json
#   baselines/p0c3/manifest.json

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Sanity checks
test -f "pyproject.toml" || { echo "ERROR: run from repo root (pyproject.toml missing)"; exit 1; }
test -f "examples/quickstart_spec.json" || { echo "ERROR: examples/quickstart_spec.json not found"; exit 1; }

BASE_DIR="baselines/p0c3"
TMP_DIR="baselines/_tmp"
mkdir -p "$BASE_DIR" "$TMP_DIR" "scripts"

# Fresh venv
if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install -U pip wheel >/dev/null
pip install -e . >/dev/null

# Compose a temp spec overlay for baseline capture
# - Write journal to baselines/p0c3/journal.csv
# - Auto-generate report.json
# - Export folder bundle (manifest.json) into baselines/p0c3
TMP_SPEC="$TMP_DIR/p0c3_quickstart_overlay.json"

python - <<'PY'
import json, pathlib
root = pathlib.Path(".")
base = pathlib.Path("baselines/p0c3")
tmp  = pathlib.Path("baselines/_tmp")
src  = root/"examples"/"quickstart_spec.json"
spec = json.loads(src.read_text())

# Force deterministic and direct outputs into baselines/p0c3
run = dict(spec.get("run", {}))
csv_cfg = dict(run.get("csv", {}))
csv_cfg.update({
    "enabled": True,
    "path": str(base/"journal.csv"),
    "append": False,
    "run_id": "P0C3",
    "seed": 123,
})
run["csv"] = csv_cfg

# Auto-report to report.json
run["report"] = {
    "enabled": True,
    "path": str(base/"report.json"),
    "auto": True,
}

# Optional meta (not strictly required but useful)
run["meta"] = {
    "enabled": True,
    "path": str(base/"meta.json"),
}

# Export bundle (folder) to generate manifest.json + versioned artifacts
run["export"] = {
    "path": str(base),
    "compress": False,
}

# Keep original roll count, but ensure seed is deterministic, even if caller passes CLI --seed
run["seed"] = 123

spec["run"] = run

tmp_file = pathlib.Path("baselines/_tmp")/"p0c3_quickstart_overlay.json"
tmp_file.parent.mkdir(parents=True, exist_ok=True)
tmp_file.write_text(json.dumps(spec, indent=2))
print(tmp_file)
PY

# Actually run the simulation via CLI
echo "▶ Running baseline with crapssim-ctl …"
crapssim-ctl run "$TMP_SPEC" --seed 123

# Verify artifacts
echo "▶ Verifying artifacts …"
test -f "$BASE_DIR/journal.csv"   || { echo "Missing $BASE_DIR/journal.csv"; exit 1; }
test -f "$BASE_DIR/report.json"   || { echo "Missing $BASE_DIR/report.json"; exit 1; }
test -f "$BASE_DIR/manifest.json" || { echo "Missing $BASE_DIR/manifest.json"; exit 1; }

# Pretty print a tiny summary
echo "✅ Baseline complete:"
echo "  - $BASE_DIR/journal.csv"
echo "  - $BASE_DIR/report.json"
echo "  - $BASE_DIR/manifest.json"
echo
echo "Manifest digest:"
python - <<'PY'
import json, pathlib
m = pathlib.Path("baselines/p0c3/manifest.json")
data = json.loads(m.read_text())
print(json.dumps({k: data.get(k) for k in ("artifacts","fingerprints")}, indent=2))
PY

echo
echo "Next steps:"
echo "  1) pytest -q"
echo "  2) git add . && git status"
echo "  3) git commit -m 'P0·C3: hygiene + baseline snapshot'"
echo "  4) git tag v0.29.0-phase0c3-baseline"
echo "  5) git push && git push --tags"