#!/usr/bin/env python3
import hashlib
import json
import pathlib
import sys

BASE = pathlib.Path("baselines/p0c3")
MANIFEST = BASE / "manifest.json"
REPORT = BASE / "report.json"
JOURNAL = BASE / "journal.csv"   # optional

def sha256(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1<<20), b""):
            h.update(chunk)
    return h.hexdigest()

def must(p: pathlib.Path, note=""):
    if not p.exists():
        print(f"ERROR: missing {p}{(' ('+note+')') if note else ''}")
        sys.exit(1)

def main():
    must(MANIFEST, "committed baseline manifest")
    exp = json.loads(MANIFEST.read_text())
    exp_fps = exp.get("fingerprints", {})

    # Verify required files exist (report always, journal optional)
    must(REPORT, "committed baseline report.json")

    # Recompute current fingerprints for the files that exist in baseline
    cur_fps = {}
    for name in ("report.json", "journal.csv"):
        p = BASE / name
        if p.exists():
            cur_fps[name] = sha256(p)

    # Compare only on keys present in the baseline manifest
    failed = []
    for name, exp_hash in exp_fps.items():
        p = BASE / name
        if not p.exists():
            failed.append(f"{name}: file missing but expected in baseline")
            continue
        cur_hash = cur_fps.get(name) or sha256(p)
        if cur_hash != exp_hash:
            failed.append(f"{name}: hash mismatch\n  expected {exp_hash}\n  got      {cur_hash}")

    if failed:
        print("❌ Baseline verification failed:\n- " + "\n- ".join(failed))
        sys.exit(2)

    print("✅ Baseline matches manifest.")
    sys.exit(0)

if __name__ == "__main__":
    main()
