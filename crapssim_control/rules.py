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


def _parse_apply_template(act: str) -> str | None:
    """
    Extract the mode name from "apply_template('Mode')" or "apply_template(\"Mode\")".
    Returns the mode string or None if the pattern doesn't match.
    """
    s = act.strip().replace(" ", "")
    if not s.startswith("apply_template(") or not s.endswith(")"):
        return None
    inside = s[len("apply_template("):-1]
    if len(inside) >= 2 and inside[0] in ("'", '"') and inside[-1] == inside[0]:
        return inside[1:-1]
    return None


def _expand_template_to_intents(spec: dict, vs: Any, mode: str) -> List[BetIntent]:
    """
    Expand spec["modes"][mode]["template"] into concrete bet intents of shape:
        (bet_kind, number_or_None, amount_expr)
    e.g. {"pass": "units", "field":"units"} -> [("pass", None, "units"), ("field", None, "units")]
    """
    modes = spec.get("modes", {})
    m = modes.get(mode, {})
    tpl = m.get("template", {})
    intents: List[BetIntent] = []
    for bet_kind, amount_expr in tpl.items():
        # craps line/field bets have no number; place/lay/come/DC may include numbers in other flows
        intents.append((bet_kind, None, amount_expr))
    return intents


def run_rules_for_event(spec: dict, vs: Any, event: Dict[str, Any]) -> List[BetIntent]:
    """
    Evaluate spec["rules"] against the given event and produce a list of "intents".
    Intents are tuples consumed by materialize.apply_intents later.

    Supported action encodings:
      - "units += 10"              -> ("__expr__", <str>, None)
      - {"pass": "units"}          -> ("__dict__", <dict>, None)
      - "apply_template('Main')"   -> expands immediately to bet tuples, e.g. ("pass", None, "units")

    We expand templates *here* because the tests expect run_rules_for_event to
    already contain concrete bet intents (they inspect kinds without calling
    templates.render_template).
    """
    intents: List[BetIntent] = []
    rules: List[dict] = spec.get("rules", [])

    for rule in rules:
        cond = rule.get("on", {})
        if match_rule(event, cond):
            actions = rule.get("do", [])
            for act in actions:
                if isinstance(act, str):
                    mode = _parse_apply_template(act)
                    if mode is not None:
                        intents.extend(_expand_template_to_intents(spec, vs, mode))
                    else:
                        intents.append(("__expr__", act, None))
                elif isinstance(act, dict):
                    intents.append(("__dict__", act, None))
                else:
                    raise ValueError(f"Unsupported action type: {act!r}")

    return intents