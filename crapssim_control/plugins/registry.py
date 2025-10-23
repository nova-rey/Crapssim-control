"""Plugin manifest parsing and registry utilities."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

import yaml

SEMVER_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+].*)?$")


@dataclass
class Capability:
    """A discrete capability exposed by a plugin."""

    kind: str
    name: str
    version: str
    entry: str


@dataclass
class PluginSpec:
    """Normalized representation of a plugin manifest."""

    name: str
    version: str
    capabilities: List[Capability]
    requires: Dict[str, str] = field(default_factory=dict)
    description: str = ""
    path: Optional[str] = None


class PluginRegistry:
    """Registry for discovering and validating plugin manifests."""

    def __init__(self) -> None:
        self._registry: Dict[Tuple[str, str, str], PluginSpec] = {}

    def discover(self, paths: Iterable[str]) -> List[PluginSpec]:
        """Scan provided paths for ``plugin.yaml`` files.

        Parameters
        ----------
        paths:
            Iterable of directory paths to scan. Non-existent entries are ignored.

        Returns
        -------
        list of PluginSpec
            Specs parsed and registered in deterministic order.
        """

        found: List[PluginSpec] = []
        for base in paths:
            if not base or not os.path.isdir(base):
                continue
            for root, _, files in os.walk(base):
                if "plugin.yaml" not in files:
                    continue
                manifest_path = os.path.join(root, "plugin.yaml")
                with open(manifest_path, "r", encoding="utf-8") as stream:
                    data = yaml.safe_load(stream) or {}
                spec = self._parse_manifest(data, manifest_path)
                if self.validate(spec):
                    self.register(spec)
                    found.append(spec)
        found.sort(key=lambda s: (s.name, s.version))
        return found

    def _parse_manifest(self, data: Dict[str, object], path: str) -> PluginSpec:
        """Parse manifest dict into :class:`PluginSpec`."""

        for key in ("name", "version", "capabilities"):
            if key not in data:
                raise ValueError(f"Missing key '{key}' in {path}")
        name = data["name"]
        version = data["version"]
        if not isinstance(name, str) or not name:
            raise ValueError(f"Plugin name must be non-empty string in {path}")
        if not isinstance(version, str) or not SEMVER_PATTERN.match(version):
            raise ValueError(f"Invalid semver '{version}' in {path}")

        raw_caps = data["capabilities"]
        if not isinstance(raw_caps, list) or not raw_caps:
            raise ValueError(f"Manifest capabilities must be a non-empty list in {path}")
        capabilities: List[Capability] = []
        for cap in raw_caps:
            if not isinstance(cap, dict):
                raise ValueError(f"Capability entry must be mapping in {path}")
            for ckey in ("kind", "name", "version", "entry"):
                if ckey not in cap:
                    raise ValueError(f"Missing capability key '{ckey}' in {path}")
                if not isinstance(cap[ckey], str) or not cap[ckey]:
                    raise ValueError(f"Capability key '{ckey}' must be non-empty string in {path}")
            if not SEMVER_PATTERN.match(cap["version"]):
                raise ValueError(f"Invalid capability semver '{cap['version']}' in {path}")
            capabilities.append(Capability(**cap))

        requires = data.get("requires", {})
        if not isinstance(requires, dict):
            raise ValueError(f"Requires section must be a mapping in {path}")
        description = data.get("description", "")
        if description and not isinstance(description, str):
            raise ValueError(f"Description must be a string in {path}")

        return PluginSpec(
            name=name,
            version=version,
            capabilities=capabilities,
            requires={str(k): str(v) for k, v in requires.items()},
            description=description,
            path=path,
        )

    def validate(self, spec: PluginSpec) -> bool:
        """Perform static checks on :class:`PluginSpec`."""

        if "." not in spec.name:
            raise ValueError(
                f"Plugin name '{spec.name}' must be in 'author.plugin' format"
            )

        existing = {(s.name, s.version) for s in self._registry.values()}
        if (spec.name, spec.version) in existing:
            return False
        return True

    def register(self, spec: PluginSpec) -> None:
        """Add :class:`PluginSpec` capabilities to registry."""

        for cap in spec.capabilities:
            key = (cap.kind, cap.name, cap.version)
            if key not in self._registry:
                self._registry[key] = spec

    def resolve(self, kind: str, name: str, version: str) -> Optional[PluginSpec]:
        """Return matching spec if present."""

        return self._registry.get((kind, name, version))

    def resolve_by_ref(self, ref_name: str, kind: str, cap_name: str, version: str) -> PluginSpec | None:
        """
        Try resolving by plugin package name (e.g., 'author.sample') + desired capability tuple.
        Returns the first spec that matches (name==ref_name and provides capability with version).
        """
        for spec in self._registry.values():
            if spec.name != ref_name:
                continue
            for cap in spec.capabilities:
                if cap.kind == kind and cap.name == cap_name and str(cap.version) == str(version):
                    return spec
        return None

    def capabilities_of(self, spec: PluginSpec) -> list[tuple[str, str, str]]:
        return [(c.kind, c.name, str(c.version)) for c in spec.capabilities]

    def all_specs(self) -> List[PluginSpec]:
        """Return all registered :class:`PluginSpec` objects."""

        seen: Dict[int, PluginSpec] = {}
        for spec in self._registry.values():
            if id(spec) not in seen:
                seen[id(spec)] = spec
        return list(seen.values())


__all__ = ["Capability", "PluginSpec", "PluginRegistry"]
