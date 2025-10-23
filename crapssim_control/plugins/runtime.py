from __future__ import annotations
import json
import os
from typing import Dict, Any, List, Tuple

from .registry import PluginRegistry
from .loader import PluginLoader, SandboxPolicy


# Existing registries remain
class VerbRegistry:
    _verbs: Dict[str, Any] = {}

    @classmethod
    def register(cls, name: str, instance: Any) -> None:
        cls._verbs[name] = instance

    @classmethod
    def get(cls, name: str) -> Any | None:
        return cls._verbs.get(name)

    @classmethod
    def clear(cls) -> None:
        cls._verbs.clear()


class PolicyRegistry:
    _policies: Dict[str, Any] = {}

    @classmethod
    def register(cls, name: str, instance: Any) -> None:
        cls._policies[name] = instance

    @classmethod
    def get(cls, name: str) -> Any | None:
        return cls._policies.get(name)

    @classmethod
    def clear(cls) -> None:
        cls._policies.clear()


def clear_registries() -> None:
    """Hard reset after each run to prevent state bleed."""
    VerbRegistry.clear()
    PolicyRegistry.clear()


def _parse_capability_id(cap_str: str) -> Tuple[str, str]:
    """
    'verb.roll_strategy' -> ('verb','roll_strategy')
    """
    parts = cap_str.split(".", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid capability id '{cap_str}' (expected kind.name)")
    return parts[0], parts[1]


def load_plugins_for_spec(
    spec_dict: Dict[str, Any],
    registry: PluginRegistry,
    loader: PluginLoader,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    reqs = spec_dict.get("use_plugins") or []
    for req in reqs:
        cap_id = req.get("capability") if isinstance(req, dict) else None
        version = ""
        ref = None
        if isinstance(req, dict):
            version = (req.get("version") or "").strip().lstrip("^")
            ref = req.get("ref")
        if not (cap_id and version and ref):
            items.append({"status": "malformed", "raw": req})
            continue
        try:
            kind, cap_name = _parse_capability_id(cap_id)
        except ValueError as exc:
            items.append({"status": "malformed", "raw": req, "error": str(exc)})
            continue

        spec = registry.resolve(kind, cap_name, version) or registry.resolve_by_ref(
            ref, kind=kind, cap_name=cap_name, version=version
        )
        if spec is None:
            items.append({
                "name": ref,
                "version": version,
                "capabilities": [f"{cap_id}/{version}"],
                "status": "missing",
            })
            continue

        try:
            inst = loader.instantiate(spec, kind=kind, cap_name=cap_name, version=version)
            if inst is None:
                items.append({
                    "name": spec.name,
                    "version": spec.version,
                    "capabilities": [f"{cap_id}/{version}"],
                    "status": "load_error",
                })
                continue
            if kind == "verb":
                VerbRegistry.register(cap_name, inst)
            elif kind == "policy":
                PolicyRegistry.register(cap_name, inst)
            else:
                items.append({
                    "name": spec.name,
                    "version": spec.version,
                    "capabilities": [f"{cap_id}/{version}"],
                    "status": f"unsupported_kind:{kind}",
                })
                continue
            items.append({
                "name": spec.name,
                "version": spec.version,
                "capabilities": [f"{cap_id}/{version}"],
                "status": "ok",
            })
        except Exception as e:
            items.append({
                "name": spec.name,
                "version": spec.version,
                "capabilities": [f"{cap_id}/{version}"],
                "status": "load_error",
                "error": str(e),
            })
    return items


def default_sandbox_policy() -> SandboxPolicy:
    return SandboxPolicy(
        allowed_modules=["math", "time"],
        deny_modules=[
            "os",
            "sys",
            "subprocess",
            "socket",
            "pathlib",
            "shutil",
            "tempfile",
            "http",
            "urllib",
        ],
        init_timeout=1.0
    )


def write_plugins_manifest(artifacts_dir: str, loaded_list: List[Dict[str, Any]]) -> str:
    """Write artifacts/plugins_manifest.json snapshot and return its path."""
    os.makedirs(os.path.join(artifacts_dir), exist_ok=True)
    snap = {"plugins_loaded": loaded_list}
    out_path = os.path.join(artifacts_dir, "plugins_manifest.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=2, sort_keys=True)
    return out_path
