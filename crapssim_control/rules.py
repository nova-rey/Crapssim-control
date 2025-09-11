"""
rules.py -- rule matcher + exported render_template passthrough.

- run_rules_for_event: evaluates spec["rules"] against an event and returns
  "intents" that the materializer later applies.
- render_template: re-exported thin wrapper around templates.render_template
  so modules importing it from rules keep working (e.g., controller.py).
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# Expose render_template here to satisfy imports like:
#   from .rules import run_rules_for_event, render_template
from .templates import render_template as _tpl_render_template

# Public type alias used conceptually by tests/materializer
BetIntent = Tuple[str, Any, Any]

__all__ = ["run_rules_for_event", "render_template"]


def render_template(spec: dict, vs: Any, intents: List[BetIntent], table_level: int | None = None):
    """
    Pass-through to the real templates.render_template implementation.
    Kept here for backward-compat/expected import path.
    """
    return _tpl_render_template(spec, vs, intents, table_level=table_level)


# ---------- Rule matching ----------

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

    Expected intent encodings:
      - Action is a string like "units += 10"
          -> ("__expr__", <str>, None)
      - Action is a dict like {"pass": "units"}
          -> ("__dict__", <dict>, None)
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