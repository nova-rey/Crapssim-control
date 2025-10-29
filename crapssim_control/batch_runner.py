import json
import os
import shutil
from typing import Any, Dict, Optional, Tuple

from .utils.dna_conveyor import (
    spec_seed_fingerprint,
    unpack_bundle,
    repack_with_artifacts,
)

# These imports are expected to exist in the project already
# Controller/single-run entrypoints should remain unchanged
try:
    from .controller import (
        run_single,
    )  # expected signature: run_single(spec_path_or_dict, out_dir) -> artifacts_dir
except Exception:  # pragma: no cover
    run_single = None  # tests will mock or skip if unavailable


def _load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load_json(path: str) -> Dict[str, Any]:
    return json.loads(_load_text(path))


def _find_spec_and_seed(root: str) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], str]:
    """
    Locate spec.json (required) and seed.json (optional) under root.
    Return (spec_dict, seed_dict_or_none, spec_path).
    """
    candidates = []
    for base, _, files in os.walk(root):
        for fn in files:
            if fn.lower() == "spec.json":
                candidates.append(os.path.join(base, fn))
    if not candidates:
        raise FileNotFoundError("spec.json not found in bundle/root")
    # Prefer top-most spec
    candidates.sort(key=lambda p: p.count(os.sep))
    spec_path = candidates[0]
    spec = _load_json(spec_path)

    seed = None
    seed_candidates = []
    for base, _, files in os.walk(root):
        for fn in files:
            if fn.lower() == "seed.json":
                seed_candidates.append(os.path.join(base, fn))
    if seed_candidates:
        seed_path = sorted(seed_candidates, key=lambda p: p.count(os.sep))[0]
        seed = _load_json(seed_path)

    return spec, seed, spec_path


def _ensure_dir(p: str) -> str:
    os.makedirs(p, exist_ok=True)
    return p


def run_single_bundle_or_spec(
    item_path: str,
    out_root: str,
    engine_version: str = "engine-unknown",
    csc_version: str = "csc-unknown",
) -> Dict[str, Any]:
    """
    Execute a single batch item. Accepts a .zip bundle or a path to spec.json.
    Returns a record for batch_manifest.
    """
    temp_dir = None
    is_zip = False
    record: Dict[str, Any] = {
        "source": item_path,
        "input_type": "zip" if item_path.lower().endswith(".zip") else "spec",
        "status": "pending",
    }
    try:
        root, is_zip = unpack_bundle(item_path)
        temp_dir = root if is_zip else None

        spec, seed, spec_path = _find_spec_and_seed(root)
        run_id = spec_seed_fingerprint(spec, seed, engine_version, csc_version)

        run_out = _ensure_dir(os.path.join(out_root, run_id))
        # Delegate to existing single-run path if available; else emit placeholders
        artifacts_dir = None
        if run_single is not None:
            artifacts_dir = run_single(spec_path_or_dict=spec, out_dir=run_out)
        else:
            # Minimal placeholder: ensure folder and write a trivial manifest
            artifacts_dir = run_out
            with open(os.path.join(artifacts_dir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {"run_id": run_id, "note": "placeholder artifacts (run_single missing)"}, f
                )

        # Always generate an output zip that preserves unknown payloads and adds artifacts/
        output_zip = os.path.join(out_root, f"{run_id}.zip")
        repack_with_artifacts(
            input_path=item_path,
            artifacts_dir=artifacts_dir,
            output_zip_path=output_zip,
            artifacts_prefix="artifacts/",
        )

        record.update(
            {
                "run_id": run_id,
                "artifacts_dir": artifacts_dir,
                "output_zip": output_zip,
                "status": "success",
            }
        )
        return record
    except Exception as e:
        record.update({"status": "error", "error": str(e)})
        return record
    finally:
        if is_zip and temp_dir and os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


def load_plan(plan_path: str) -> Dict[str, Any]:
    """
    Minimal plan loader supporting YAML (if PyYAML available) or JSON.
    Expected format:
      items:
        - path: specs/iron_cross.json
        - path: inputs/gen1/child_07.zip
      out_dir: exports/
    """
    text = _load_text(plan_path)
    # Try JSON first for deterministic plans
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback to YAML if available
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except Exception:
        raise


def run_batch(plan_path: str) -> Dict[str, Any]:
    plan = load_plan(plan_path)
    if not isinstance(plan, dict):
        raise TypeError("Batch plan must be a mapping")
    raw_items = plan.get("items", [])
    items = []
    for entry in raw_items:
        if isinstance(entry, dict) and "path" in entry:
            items.append(entry["path"])
        elif isinstance(entry, str):
            items.append(entry)
        else:
            raise TypeError(f"Unsupported plan entry: {entry!r}")
    out_root = plan.get("out_dir", "exports")
    _ensure_dir(out_root)

    # TODO: fetch actual versions from runtime surface if available
    engine_version = plan.get("engine_version", "engine-unknown")
    csc_version = plan.get("csc_version", "csc-unknown")

    batch_manifest = {
        "plan": os.path.basename(plan_path),
        "out_dir": out_root,
        "items": [],
    }
    for p in items:
        rec = run_single_bundle_or_spec(
            item_path=p,
            out_root=out_root,
            engine_version=engine_version,
            csc_version=csc_version,
        )
        batch_manifest["items"].append(rec)

    manifest_path = os.path.join(out_root, "batch_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(batch_manifest, f, indent=2, sort_keys=True)
    return batch_manifest
