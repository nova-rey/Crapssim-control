import json
import sys
import pathlib


def _ok(msg):  # print green-ish without deps
    print(f"[OK] {msg}")


def _warn(msg):
    print(f"[WARN] {msg}")


def _err(msg):
    print(f"[ERR] {msg}")


REQUIRED_TOP_KEYS = {"schema_version", "table", "profiles", "run"}


def run(spec_path: str | None = None):
    if spec_path is None:
        spec_path = "spec.json"
    spec_file = pathlib.Path(spec_path)
    exit_code = 0

    if not spec_file.exists():
        _err(f"Missing spec file: {spec_file}")
        print("Hint: run `csc init .` to scaffold a skeleton.")
        sys.exit(2)

    try:
        spec = json.loads(spec_file.read_text())
    except Exception as e:
        _err(f"Failed to parse JSON: {e}")
        sys.exit(2)

    missing = REQUIRED_TOP_KEYS - set(spec.keys())
    if missing:
        _err(f"Spec missing required keys: {sorted(missing)}")
        exit_code = 2
    else:
        _ok("Spec has required top-level keys")

    if "schema_version" in spec and not isinstance(spec["schema_version"], str):
        _warn("schema_version should be a string (e.g., '1.0')")

    table = spec.get("table", {})
    if "odds" not in table:
        _warn("table.odds not set (e.g., '3-4-5x')")

    profiles = spec.get("profiles", {})
    if "default" not in profiles:
        _warn("profiles.default not defined")

    run = spec.get("run", {})
    if "csv" not in run or "embed_analytics" not in run.get("csv", {}):
        _warn("run.csv.embed_analytics not set (defaults may apply)")

    if exit_code == 0:
        _ok("Doctor finished with no fatal errors")
    sys.exit(exit_code)
