"""Rule Authoring Aids (v1).

Provides macros, parameter expansion, and linting for rule specs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

from crapssim_control.rules_engine.actions import ACTIONS
from crapssim_control.rules_engine.schema import validate_ruleset

__all__ = ["RuleBuilder"]


PLACEHOLDER_PATTERN = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
IDENT_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")

SAFE_VARS = {
    "bankroll_after",
    "drawdown_after",
    "hand_id",
    "roll_in_hand",
    "point_on",
    "last_roll_total",
    "box_hits",
    "dc_losses",
    "dc_wins",
}

RESERVED_TOKENS = {
    "and",
    "or",
    "not",
    "in",
    "True",
    "False",
    "None",
    "abs",
    "min",
    "max",
    "round",
}


class RuleBuilder:
    """Macro expansion and lint helpers for authoring rule specs."""

    def __init__(self, macros_file: Optional[str] = None) -> None:
        self.macros: Dict[str, Dict[str, Any]] = {}
        if macros_file:
            path = Path(macros_file)
            if path.is_file():
                with path.open("r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
                    macros = data.get("macros", {}) if isinstance(data, dict) else {}
                    if isinstance(macros, dict):
                        self.macros = macros

    # ------------------------------------------------------------------
    # Macro / Spec Expansion
    # ------------------------------------------------------------------
    def expand(self, spec_path: str | Path) -> List[Dict[str, Any]]:
        """Expand macros and parameterized rules from YAML/JSON spec."""

        with Path(spec_path).open("r", encoding="utf-8") as fh:
            spec = yaml.safe_load(fh)

        if isinstance(spec, list):
            # Already a fully-specified rule list.
            return json.loads(json.dumps(spec))

        if not isinstance(spec, dict):
            raise ValueError(f"Rule spec must be dict or list, got {type(spec)!r}")

        use = spec.get("use")
        if not isinstance(use, str):
            raise ValueError(f"Spec {spec_path} missing 'use' macro reference")

        params = spec.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise ValueError(f"Spec params must be a mapping, got {type(params)!r}")

        base = self.macros.get(use)
        if not base:
            raise ValueError(f"Unknown macro '{use}' in {spec_path}")

        expanded = self._deep_copy(base)
        for key, val in params.items():
            expanded = self._substitute(expanded, key, val)

        expanded.setdefault("id", f"{use}_001")
        return [expanded]

    # ------------------------------------------------------------------
    # Linting
    # ------------------------------------------------------------------
    def lint(self, rules: Iterable[Dict[str, Any]]) -> List[str]:
        """Perform variable and action sanity checks."""

        warnings: List[str] = []
        rules_list = list(rules)
        for rule in rules_list:
            rid = rule.get("id", "<unknown>")

            exprs = [rule.get("when"), rule.get("guard")]
            for expr in exprs:
                if not isinstance(expr, str):
                    continue
                unknown_tokens: set[str] = set()
                for var in PLACEHOLDER_PATTERN.findall(expr):
                    if var in SAFE_VARS:
                        continue
                    if var in unknown_tokens:
                        continue
                    warnings.append(f"{rid}: unknown variable '{var}'")
                    unknown_tokens.add(var)
                for match in IDENT_PATTERN.finditer(expr):
                    token = match.group(1)
                    if token in unknown_tokens:
                        continue
                    if token in SAFE_VARS or token in RESERVED_TOKENS:
                        continue
                    if token.isdigit():
                        continue
                    # Skip tokens that are part of quoted strings
                    start, end = match.span(1)
                    if start > 0 and expr[start - 1] in {'"', "'"}:
                        continue
                    if end < len(expr) and expr[end] in {'"', "'"}:
                        continue
                    warnings.append(f"{rid}: unknown variable '{token}'")
                    unknown_tokens.add(token)

            action_text = rule.get("action", "")
            if isinstance(action_text, str):
                verb = action_text.split("(", 1)[0].strip()
            else:
                verb = ""
            if verb and verb not in ACTIONS:
                warnings.append(f"{rid}: unknown action verb '{verb}'")

        schema_errors = validate_ruleset(rules_list)
        warnings.extend(schema_errors)
        return warnings

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def save(self, rules: List[Dict[str, Any]], path: str | Path) -> None:
        """Save expanded and validated rules to JSON."""

        with Path(path).open("w", encoding="utf-8") as fh:
            json.dump(rules, fh, indent=2)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _substitute(self, data: Any, key: str, val: Any) -> Any:
        """Recursive parameter substitution for ``$key`` placeholders."""

        placeholder = f"${key}"
        if isinstance(data, str):
            return data.replace(placeholder, str(val))
        if isinstance(data, dict):
            return {k: self._substitute(v, key, val) for k, v in data.items()}
        if isinstance(data, list):
            return [self._substitute(item, key, val) for item in data]
        return data

    @staticmethod
    def _deep_copy(data: Dict[str, Any]) -> Dict[str, Any]:
        """JSON-compatible deep copy helper."""

        return json.loads(json.dumps(data))

