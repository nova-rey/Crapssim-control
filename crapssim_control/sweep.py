import itertools
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

# Reuse the C1 batch runner
from . import batch_runner


# Optional YAML dependency; fall back to JSON
def _load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load_struct(path: str) -> Dict[str, Any]:
    text = _load_text(path)
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"Unsupported plan structure in {path}; expected object")
    return data


def _dump_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)


def _safe(val: Any) -> str:
    s = str(val)
    s = re.sub(r"[^A-Za-z0-9_.-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "x"


def _name_from_vars(base: str, kvs: Dict[str, Any]) -> str:
    parts = [base]
    for k in sorted(kvs.keys()):
        parts.append(f"{_safe(k)}-{_safe(kvs[k])}")
    return "__".join(parts) + ".json"


@dataclass
class ExpandedItem:
    path: str  # filesystem path to spec (or original .zip path)
    input_type: str  # "spec" or "zip"


def _expand_explicit(plan: Dict[str, Any]) -> Tuple[List[ExpandedItem], str]:
    out_dir = plan.get("out_dir", "exports")
    items = []
    for it in plan.get("items", []):
        p = it["path"]
        if str(p).lower().endswith(".zip"):
            items.append(ExpandedItem(path=p, input_type="zip"))
        else:
            items.append(ExpandedItem(path=p, input_type="spec"))
    return items, out_dir


def _expand_grid(plan: Dict[str, Any]) -> Tuple[List[ExpandedItem], str]:
    """
    Grid expansion: cartesian product of listed vars; write temp spec copies with substituted values.
    We do NOT mutate .zip inputs in grid mode; only template-driven spec expansion is supported here.
    """
    out_dir = plan.get("out_dir", "exports")
    template_path = plan["template"]
    vars_map: Dict[str, List[Any]] = plan.get("vars", {})
    # Safety limit
    max_items = int(plan.get("max_items", 200))
    keys = list(vars_map.keys())
    values_product = list(itertools.product(*[vars_map[k] for k in keys])) if keys else [()]
    if len(values_product) > max_items and not plan.get("force", False):
        raise ValueError(
            f"Grid expansion ({len(values_product)}) exceeds max_items={max_items}. Use force:true to override."
        )

    # Load template spec
    with open(template_path, "r", encoding="utf-8") as f:
        base_spec = json.load(f)

    # Write expanded specs under a temp dir colocated with out_dir for determinism and cleanup
    sweep_root = plan.get("sweep_root") or os.path.join(out_dir, "_sweep_specs")
    os.makedirs(sweep_root, exist_ok=True)

    # Determine a readable base name
    base_name = os.path.splitext(os.path.basename(template_path))[0]
    expanded: List[ExpandedItem] = []
    for combo in values_product:
        kv = {k: v for k, v in zip(keys, combo)}
        spec = json.loads(json.dumps(base_spec))  # deep copy
        # Shallow insert of vars at top-level keys; advanced templating can come later
        for k, v in kv.items():
            spec[k] = v
        fn = _name_from_vars(base_name, kv)
        out_spec_path = os.path.join(sweep_root, fn)
        _dump_json(out_spec_path, spec)
        expanded.append(ExpandedItem(path=out_spec_path, input_type="spec"))
    return expanded, out_dir


def expand_plan(plan_path: str) -> Tuple[List[ExpandedItem], str, Dict[str, Any]]:
    plan = _load_struct(plan_path)
    mode = (plan.get("mode") or "explicit").lower()
    if mode == "explicit":
        items, out_dir = _expand_explicit(plan)
    elif mode == "grid":
        items, out_dir = _expand_grid(plan)
    else:
        raise ValueError(f"Unsupported sweep mode: {mode}")
    return items, out_dir, plan


def _to_batch_plan(items: List[ExpandedItem], out_dir: str, base: Dict[str, Any]) -> Dict[str, Any]:
    bp = {
        "items": [{"path": it.path} for it in items],
        "out_dir": out_dir,
    }
    # Allow passing versions through for hashing determinism if provided
    if "engine_version" in base:
        bp["engine_version"] = base["engine_version"]
    if "csc_version" in base:
        bp["csc_version"] = base["csc_version"]
    return bp


def run_sweep(plan_path: str) -> str:
    """
    Expand the sweep plan, write a transient batch plan, call batch runner, and return path to batch_manifest.json.
    """
    items, out_dir, base = expand_plan(plan_path)
    batch_plan = _to_batch_plan(items, out_dir, base)
    # Serialize the derived batch plan next to the input sweep plan for traceability
    derived_batch_plan_path = os.path.join(out_dir, "derived_batch_plan.json")
    os.makedirs(out_dir, exist_ok=True)
    _dump_json(derived_batch_plan_path, batch_plan)
    # Execute
    manifest = batch_runner.run_batch(derived_batch_plan_path)
    # The batch runner writes batch_manifest.json at out_dir
    manifest_path = os.path.join(out_dir, "batch_manifest.json")
    # If an alternate location is ever returned, prefer what was written to disk
    if not os.path.isfile(manifest_path):
        # Fallback: write what we got
        _dump_json(manifest_path, manifest)
    return manifest_path
