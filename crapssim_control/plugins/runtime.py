from __future__ import annotations
from typing import Dict, Any, List, Tuple

from .registry import PluginRegistry, PluginSpec
from .loader import PluginLoader, SandboxPolicy


# Simple in-process registries for bound capabilities
class VerbRegistry:
    _verbs: Dict[str, Any] = {}

    @classmethod
    def register(cls, name: str, instance: Any) -> None:
        cls._verbs[name] = instance

    @classmethod
    def get(cls, name: str) -> Any | None:
        return cls._verbs.get(name)


class PolicyRegistry:
    _policies: Dict[str, Any] = {}

    @classmethod
    def register(cls, name: str, instance: Any) -> None:
        cls._policies[name] = instance

    @classmethod
    def get(cls, name: str) -> Any | None:
        return cls._policies.get(name)


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
    """
    Reads spec_dict["use_plugins"] and loads/instantiates requested capabilities.
    Returns a list of dicts to be merged into manifest under 'plugins_loaded'.
    Each entry: {"name": "...", "version": "...", "capabilities": ["verb.roll_strategy/1.0.0"]}
    """
    items: List[Dict[str, Any]] = []
    reqs = spec_dict.get("use_plugins") or []
    for req in reqs:
        if not isinstance(req, dict):
            items.append({"status": "invalid_entry"})
            continue
        cap_id = req.get("capability")
        version = (req.get("version") or "").strip().lstrip("^")  # minimal support: exact version fallback
        ref = req.get("ref")  # plugin name e.g. "author.sample"
        if not (cap_id and version and ref):
            raise ValueError(f"Malformed use_plugins entry: {req}")

        kind, cap_name = _parse_capability_id(cap_id)
        spec: PluginSpec | None = registry.resolve(kind, cap_name, version)
        # If no direct resolve, try by ref name match (plugin name)
        if spec is None:
            spec = registry.resolve_by_ref(ref, kind=kind, cap_name=cap_name, version=version)

        if spec is None:
            # Fail-closed: nothing registered; record attempted request
            items.append({"name": ref, "version": version, "capabilities": [f"{cap_id}/{version}"], "status": "missing"})
            continue

        # Instantiate class for this capability
        try:
            inst = loader.instantiate(spec, kind=kind, cap_name=cap_name, version=version)
        except Exception:
            inst = None
        if inst is None:
            items.append({"name": spec.name, "version": spec.version, "capabilities": [f"{cap_id}/{version}"], "status": "load_error"})
            continue

        # Register
        if kind == "verb":
            VerbRegistry.register(cap_name, inst)
        elif kind == "policy":
            PolicyRegistry.register(cap_name, inst)
        else:
            items.append({"name": spec.name, "version": spec.version, "capabilities": [f"{cap_id}/{version}"], "status": f"unsupported_kind:{kind}"})
            continue

        items.append({"name": spec.name, "version": spec.version, "capabilities": [f"{cap_id}/{version}"], "status": "ok"})
    return items


def default_sandbox_policy() -> SandboxPolicy:
    # Conservative defaults; allow 'math' only. Tests adjust as needed.
    return SandboxPolicy(
        allowed_modules=["math", "time"],  # time allowed for short init where needed; execution still bounded
        deny_modules=["os", "sys", "subprocess", "socket", "pathlib", "shutil", "tempfile", "http", "urllib"],
        init_timeout=1.0
    )
