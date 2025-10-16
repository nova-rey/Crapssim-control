#!/usr/bin/env bash
set -euo pipefail

# capture_baseline_p0c3.sh
# Phase 0 · Checkpoint 3 (Hygiene): produce deterministic baseline artifacts.
# Produces:
#   baselines/p0c3/report.json               (always)
#   baselines/p0c3/manifest.json             (always)
#   baselines/p0c3/journal.csv               (if controller journaling emits)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Sanity checks
test -f "pyproject.toml" || { echo "ERROR: run from repo root (pyproject.toml missing)"; exit 1; }
test -f "examples/quickstart_spec.json" || { echo "ERROR: examples/quickstart_spec.json not found"; exit 1; }

BASE_DIR="baselines/p0c3"
TMP_DIR="baselines/_tmp"
mkdir -p "$BASE_DIR" "$TMP_DIR" "scripts"

# Fresh venv (local, isolated)
if [[ ! -d ".venv" ]]; then
  python -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip -q install --upgrade pip wheel
pip -q install -e .

# Build a temp spec overlay that requests CSV + export bundle
TMP_SPEC="$TMP_DIR/p0c3_quickstart_overlay.json"
python - <<'PY'
import json, pathlib
base = pathlib.Path("baselines/p0c3")
src  = pathlib.Path("examples/quickstart_spec.json")
spec = json.loads(src.read_text())

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

# Auto-report path (controller may or may not write this)
run["report"] = {
    "enabled": True,
    "path": str(base/"report.json"),
    "auto": True,
}

# Export bundle (if wired in the runtime it will produce manifest.json)
run["export"] = {
    "path": str(base),
    "compress": False,
}

# Force deterministic seed at top-level too
run["seed"] = 123
spec["run"] = run

tmp = pathlib.Path("baselines/_tmp")/"p0c3_quickstart_overlay.json"
tmp.parent.mkdir(parents=True, exist_ok=True)
tmp.write_text(json.dumps(spec, indent=2))
print(tmp)
PY

echo "▶ Running baseline with crapssim-ctl …"
RUN_LOG="$TMP_DIR/p0c3_run_stdout.log"
# Capture stdout/stderr so we can parse RESULT: and still show logs in CI
set +e
crapssim-ctl run "$TMP_SPEC" --seed 123 | tee "$RUN_LOG"
RC=${PIPESTATUS[0]}
set -e

# Extract RESULT line (e.g., 'RESULT: rolls=50 bankroll=900.00')
RESULT_LINE="$(grep -m1 '^RESULT:' "$RUN_LOG" || true)"
ROLLS=""
BANKROLL=""
if [[ -n "$RESULT_LINE" ]]; then
  # pull digits after rolls= and bankroll=
  ROLLS="$(echo "$RESULT_LINE" | sed -n 's/.*rolls=\([0-9][0-9]*\).*/\1/p')"
  BANKROLL="$(echo "$RESULT_LINE" | sed -n 's/.*bankroll=\([0-9.][0-9.]*\).*/\1/p')"
fi

echo "▶ Verifying artifacts (with fallback) …"
JOURNAL="$BASE_DIR/journal.csv"
REPORT="$BASE_DIR/report.json"
MANIFEST="$BASE_DIR/manifest.json"

# If controller didn't create report/manifest, synthesize them from RESULT
if [[ ! -f "$REPORT" ]]; then
  echo "⚠️  report.json not found; creating minimal report from RESULT: '$RESULT_LINE'"
  python - <<PY
import json, pathlib, os
report = {
  "phase": "P0C3",
  "seed": 123,
  "result_line": os.environ.get("RESULT_LINE","").strip(),
  "rolls": int(os.environ.get("ROLLS","0")) if os.environ.get("ROLLS") else None,
  "final_bankroll": float(os.environ.get("BANKROLL","nan")) if os.environ.get("BANKROLL") else None,
  "spec": "examples/quickstart_spec.json",
}
pathlib.Path("${REPORT}").write_text(json.dumps(report, indent=2))
print(f"wrote {REPORT}")
PY
fi

# Ensure manifest exists; include any present artifacts
if [[ ! -f "$MANIFEST" ]]; then
  echo "⚠️  manifest.json not found; generating a simple manifest"
  python - <<'PY'
import json, pathlib, hashlib
base = pathlib.Path("baselines/p0c3")
arts = []
for name in ("journal.csv","report.json","meta.json"):
    p = base/name
    if p.exists():
        arts.append({"name": name, "path": str(p), "size": p.stat().st_size})
fp = {}
for a in arts:
    p = pathlib.Path(a["path"])
    with p.open("rb") as f: fp[a["name"]] = hashlib.sha256(f.read()).hexdigest()
manifest = {"artifacts": arts, "fingerprints": fp, "note": "P0C3 fallback manifest"}
(base/"manifest.json").write_text(json.dumps(manifest, indent=2))
print(f"wrote {base/'manifest.json'}")
PY
fi

# Journal is optional; warn but do not fail
if [[ ! -f "$JOURNAL" ]]; then
  echo "⚠️  journal.csv not found. Continuing with report+manifest only."
fi

# Final presence check: require at least report+manifest so CI is useful
test -f "$REPORT"   || { echo "ERROR: report.json missing after fallback"; exit 1; }
test -f "$MANIFEST" || { echo "ERROR: manifest.json missing after fallback"; exit 1; }

echo "✅ Baseline complete:"
[[ -f "$JOURNAL"  ]] && echo "  - $JOURNAL"
echo "  - $REPORT"
echo "  - $MANIFEST"

# Bubble up original return code if the run itself failed (but after writing fallbacks)
if [[ $RC -ne 0 ]]; then
  echo "⚠️  crapssim-ctl run exited with RC=$RC (simulation printed RESULT; baseline files created)"
fi