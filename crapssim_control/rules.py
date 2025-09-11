"""
rules.py -- minimal rule runner that the tests expect.

- Produces "intents" based on spec["rules"] when an event dictionary arrives.
- Does NOT execute expressions here; it returns "__expr__" / "__dict__" intents
  that are later applied by the materializer layer.
- Imports render_template only for type hints / parity with controller imports.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional

# Controller imports this symbol from here, so keep the name stable:
from .templates import render_template as _render_template  # noqa: F401  (imported for parity)

# Type alias the tests use conceptually
BetIntent = Tuple[str, Any, Any]


def _get(d: Any, key: str, default: Any = None) -> Any:
    if isinstance(d, dict):
        return d.get(key, default)
    return getattr(d, key, default)


def match_rule(event: Dict[str, Any], cond: Dict[str, Any]) -> bool:
    """
    Return True if all keys in `cond` match the same keys in `event`.
    Shallow 'AND' match; keys absent in `event` -> mismatch.
    """
    if not cond:
        return False
    for k, v in cond.items():
        if event.get(k, object()) != v:
            return False
    return True


def run_rules_for_event(spec: dict, vs: Any, event: Dict[str, Any]) -> List[BetIntent]:
    """
    Evaluate spec["rules"] against the given event and produce a list of "intents".
    Intents are tuples consumed by materialize.apply_intents later.

    Test expectations:
      - If an action is a string like "units += 10" → ("__expr__", <str>, None)
      - If an action is a dict like {"pass": "units"} → ("__dict__", <dict>, None)
      - We never emit bare 2-tuples; always length 3 (or 4 elsewhere in stack).
    """
    intents: List[BetIntent] = []
    rules: List[dict] = spec.get("rules", [])

    for rule in rules:
        cond = rule.get("on", {})
        if match_rule(event, cond):
            actions = rule.get("do", [])
            for act in actions:
                if isinstance(act, str):
                    intents.append(("__expr__", act, None))
                elif isinstance(act, dict):
                    intents.append(("__dict__", act, None))
                else:
                    raise ValueError(f"Unsupported action type: {act!r}")

    return intents