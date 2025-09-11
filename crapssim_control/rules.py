from __future__ import annotations
from typing import Any, Dict, List

from .varstore import VarStore
from .materialize import BetIntent

def match_rule(event: Dict[str, Any], cond: Dict[str, Any]) -> bool:
    """
    Return True if event dict matches the condition dict.
    All keys in cond must be present in event and equal.
    """
    for k, v in cond.items():
        if event.get(k) != v:
            return False
    return True


def run_rules_for_event(spec: dict, vs: VarStore, event: Dict[str, Any]) -> List[BetIntent]:
    """
    Evaluate the strategy rules in spec against the given event and VarStore.
    Returns a list of BetIntents.
    """
    intents: List[BetIntent] = []
    rules: List[dict] = spec.get("rules", [])

    # Some rules/tests expect to see the current event injected into user space
    if hasattr(vs, "user"):
        vs.user["_event"] = event.get("event")

    for rule in rules:
        cond = rule.get("on", {})
        if match_rule(event, cond):
            actions = rule.get("do", [])
            for act in actions:
                if isinstance(act, str):
                    intents.append(("__expr__", act))
                elif isinstance(act, dict):
                    intents.append(("__dict__", act))
                else:
                    raise ValueError(f"Unsupported action type: {act!r}")
    return intents


# ---- compatibility shim for legacy import path (rules.render_template) ----
from typing import Optional, Tuple

try:
    # The real implementation lives in templates.py
    from .templates import render_template as _render_template
except Exception as exc:  # pragma: no cover
    _templates_import_error = exc
    _render_template = None  # type: ignore[name-defined]

def render_template(
    spec: Dict[str, Any],
    vs,  # VarStore (kept untyped here to avoid import cycles)
    intents: List[Tuple],
    table_level: Optional[int] = None,
):
    """
    Compatibility wrapper so callers importing `render_template` from `rules`
    continue to work. Forwards directly to templates.render_template, preserving
    the expected call signature used by controller/tests.
    """
    if _render_template is None:
        raise ImportError(
            f"templates.render_template is unavailable: {_templates_import_error!r}"
        )
    return _render_template(spec, vs, intents, table_level)
# ---- end shim ----