"""Spec loading and normalization helpers for CrapsSim Control."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:  # Optional YAML support mirrors cli.py
    import yaml  # type: ignore
except Exception:  # pragma: no cover - PyYAML optional
    yaml = None

# Additional normalization keys can be cataloged here as new legacy fields surface
# (e.g., odds_working_on_comeout_come, pass_odds_cap, etc.).
DEPRECATED_KEY_MAP: Dict[str, str] = {
    "odds_working_on_comeout": "working_on_comeout",
}


def normalize_deprecated_keys(spec: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """Normalize shallow deprecated spec keys.

    Returns the (possibly mutated) spec alongside a list of deprecation records
    describing the actions taken for each legacy key encountered.
    """

    deprecations: List[Dict[str, str]] = []

    for old_key, new_key in DEPRECATED_KEY_MAP.items():
        if old_key in spec:
            if new_key in spec:
                spec.pop(old_key, None)
                deprecations.append(
                    {
                        "old": old_key,
                        "new": new_key,
                        "action": "kept_new_dropped_old",
                    }
                )
            else:
                spec[new_key] = spec.pop(old_key)
                deprecations.append(
                    {
                        "old": old_key,
                        "new": new_key,
                        "action": "migrated",
                    }
                )

    existing = spec.get("_csc_spec_deprecations")
    if isinstance(existing, list):
        for record in deprecations:
            if record not in existing:
                existing.append(record)
    else:
        spec["_csc_spec_deprecations"] = list(deprecations)
    return spec, deprecations


def load_spec_file(path: str | Path) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """Load a spec from JSON or YAML, applying deprecated key normalization."""

    p = Path(path)
    text = p.read_text(encoding="utf-8")

    if p.suffix.lower() in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML not installed; cannot read YAML specs.")
        data: Any = yaml.safe_load(text) or {}
    else:
        data = json.loads(text or "{}")

    if not isinstance(data, dict):
        raise ValueError("Spec root must be a JSON/YAML object (mapping).")

    spec, deprecations = normalize_deprecated_keys(data)
    return spec, deprecations
