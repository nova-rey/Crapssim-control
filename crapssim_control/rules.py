from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# We re-export render_template because other modules import it from here.
from .templates import render_template  # type: ignore
from .eval import safe_eval  # expression evaluator used by specs


BetIntent = Tuple[str, Any, Any] | Tuple[str, Any, Any, Any]


def _parse_apply_template(expr: str) -> Optional[str]:
    """
    Parse strings like:
        "apply_template('Main')"
        "apply_template(\"Aggressive\")"
    Return the mode name, or None if it doesn't match.
    """
    s = expr.strip().replace(" ", "")
    if not s.startswith("apply_template(") or not s.endswith(")"):
        return None
    inner = s[len("apply_template(") : -1]
    # Strip quotes if present
    if (inner.startswith("'") and inner.endswith("'")) or (
        inner.startswith('"') and inner.endswith('"')
    ):
        inner = inner[1:-1]
    return inner or None


def _expand_template_to_intents(spec: dict, vs: Any, mode: str) -> List[BetIntent]:
    """
    Delegate to templates.render_template, which returns a list of bet intents.
    """
    try:
        intents = render_template(spec, vs, mode)
    except Exception as e:
        raise ValueError(f"Failed to render template for mode '{mode}': {e}") from e
    return intents or []


def match_rule(event: Dict[str, Any], cond: Dict[str, Any]) -> bool:
    """
    Return True if all key/value pairs in `cond` match those in `event`.

    Examples:
      cond={"event":"bet_resolved","bet":"pass","result":"lose"}
      will only match when event has at least those keys with exactly those values.
    """
    for k, v in (cond or {}).items():
        if event.get(k) != v:
            return False
    return True


def run_rules_for_event(spec: dict, vs: Any, event: Dict[str, Any]) -> List[BetIntent]:
    """
    Given a strategy spec, a VarStore-like `vs`, and an event dict,
    return a list of bet intents to apply.

    Behavior:
      - Ensures `vs.user` exists and points at `vs.variables`.
      - Sets vs.user["_event"] = event["event"] (if available) for expressions.
      - For string actions:
          * If "apply_template('Mode')" → expand to bet intents via templates.
          * Otherwise evaluate the expression immediately with safe_eval (so tests
            that read vs.user right after this call can see the new values).
      - For dict actions:
          * Return them as ("__dict__", action, None) so the materializer can handle.

    We ALSO include a record of expressions as ("__expr__", <code>, None)
    just for observability; they do not drive bets by themselves.
    """
    intents: List[BetIntent] = []
    rules: List[dict] = spec.get("rules", [])

    # Ensure vs.user exists (tests read & mutate vs.user["..."])
    if not hasattr(vs, "user") or vs.user is None:
        try:
            vs.user = vs.variables  # alias to variables for convenience
        except Exception:
            vs.user = {}

    # Record the current event name for expressions to read.
    if isinstance(vs.user, dict):
        vs.user["_event"] = event.get("event")

    for rule in rules:
        cond = rule.get("on", {})
        if match_rule(event, cond):
            for act in rule.get("do", []):
                if isinstance(act, str):
                    mode = _parse_apply_template(act)
                    if mode is not None:
                        # Expand template to concrete bet intents
                        intents.extend(_expand_template_to_intents(spec, vs, mode))
                    else:
                        # Apply side-effect expression immediately
                        safe_eval(act, vs)
                        intents.append(("__expr__", act, None))
                elif isinstance(act, dict):
                    intents.append(("__dict__", act, None))
                else:
                    raise ValueError(f"Unsupported action type in rule: {act!r}")

    return intents