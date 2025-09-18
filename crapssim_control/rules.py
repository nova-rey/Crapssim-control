from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .eval import evaluate
from .templates import render_template  # spec-time template → {bet_type: amount}


# Map a bet_type string from a template into the (bet, number) pair that tests expect
# Examples:
#   "pass_line" → ("pass", None)
#   "place_6"   → ("place", 6)
def _kind_number(bet_type: str) -> Tuple[str | None, int | None]:
    if bet_type == "pass_line":
        return ("pass", None)
    if bet_type.startswith("place_"):
        try:
            return ("place", int(bet_type.split("_", 1)[1]))
        except Exception:
            return (None, None)
    # Extend mapping here if future tests need more
    return (None, None)


def _template_to_intents(spec: Dict[str, Any], vs: Any, mode_name: str) -> List[Tuple]:
    """
    Materialize the given mode's template (if any) using the current variable store.
    Returns a list of tuple intents: (bet, number, "set", amount)
    """
    modes = spec.get("modes", {})
    mode = modes.get(mode_name) or {}
    tmpl = mode.get("template") or {}

    # Build state for expression evaluation: system first, then user/variables (user wins).
    # render_template expects a dict of concrete values or evaluable expressions already
    state: Dict[str, Any] = {}
    state.update(getattr(vs, "system", {}) or {})
    user = getattr(vs, "user", None)
    if user is None:
        user = getattr(vs, "variables", {}) or {}
    state.update(user)

    bets = render_template(tmpl, state)  # {bet_type: amount}
    out: List[Tuple] = []
    for bet_type, amount in bets.items():
        bet, number = _kind_number(bet_type)
        out.append((bet, number, "set", float(amount)))
    return out


def run_rules_for_event(
    spec: Dict[str, Any],
    ctrl_state: Any,
    event: Dict[str, Any],
    current_bets: Dict[str, Dict] | None = None,
    table_cfg: Dict[str, Any] | None = None,
) -> List[Tuple]:
    """
    Helper used by tests to run the controller/rules and convert actions into
    simple tuples: (bet, number, action, amount)

    Expected behavior per tests:
      - On "comeout" (when no explicit rule matches), apply the active mode template.
      - When rules match, execute each "do" statement in order:
           * variable mutations like "units += 10"
           * apply_template('ModeName') to emit tuple intents
    """
    intents: List[Tuple] = []

    # ----- 1) Match rules on the event dict -----
    rules = spec.get("rules", [])
    matched: List[Dict[str, Any]] = []
    for rule in rules:
        cond = rule.get("on", {})
        if all(event.get(k) == v for k, v in cond.items()):
            matched.append(rule)

    # ----- 2) Helper to apply a template into tuple intents -----
    def _apply_template(mode_name: str | None = None) -> None:
        # Determine default mode from ctrl_state if not provided
        if mode_name is None:
            mode_name = (
                getattr(ctrl_state, "user", {}).get("mode")
                or getattr(ctrl_state, "variables", {}).get("mode")
                or next(iter(spec.get("modes", {}) or {"Main": {}}).keys())
            )
        intents.extend(_template_to_intents(spec, ctrl_state, mode_name))

    # ----- 3) Execute matched rules -----
    for rule in matched:
        for stmt in rule.get("do", []):
            s = stmt.strip()
            if s.startswith("apply_template"):
                # Supports:
                #   apply_template()
                #   apply_template('Aggressive')
                rest = s.removeprefix("apply_template").strip()
                if rest.startswith("(") and rest.endswith(")"):
                    inner = rest[1:-1].strip()
                    if inner:
                        # Strip quotes if present
                        if (inner.startswith("'") and inner.endswith("'")) or (inner.startswith('"') and inner.endswith('"')):
                            inner = inner[1:-1]
                        _apply_template(inner)
                    else:
                        _apply_template(None)
                else:
                    _apply_template(None)
            else:
                # Mutate ctrl_state.user if available, otherwise .variables
                state = getattr(ctrl_state, "user", None)
                if state is None:
                    state = getattr(ctrl_state, "variables", {})
                evaluate(s, state, event)

    # ----- 4) If nothing matched and this is "comeout", auto-apply active mode template -----
    if not matched and event.get("event") == "comeout":
        _apply_template(None)

    return intents