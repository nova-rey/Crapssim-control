from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .eval import evaluate
from .templates import render_template  # spec-time: returns {bet_type: amount}


def _kind_number(bet_type: str) -> Tuple[str | None, int | None]:
    """Map template bet_type → (bet, number) pairs expected by tests."""
    if bet_type == "pass_line":
        return ("pass", None)
    if bet_type.startswith("place_"):
        try:
            return ("place", int(bet_type.split("_", 1)[1]))
        except Exception:
            return (None, None)
    return (None, None)


def _get_bubble_and_level(spec: Dict[str, Any], vs: Any) -> Tuple[bool, int]:
    """Resolve bubble and table_level from VarStore.system or spec['table'] with safe fallbacks."""
    sys = getattr(vs, "system", {}) or {}
    bubble = sys.get("bubble")
    table_level = sys.get("table_level")

    if bubble is None or table_level is None:
        tbl = spec.get("table", {}) or {}
        if bubble is None:
            bubble = bool(tbl.get("bubble", False))
        if table_level is None:
            # some specs use "level", others "table_level"
            table_level = int(tbl.get("table_level", tbl.get("level", 10)))

    # final safety
    return bool(bubble), int(table_level)


def _template_to_intents(spec: Dict[str, Any], vs: Any, mode_name: str) -> List[Tuple]:
    """
    Materialize the given mode's template into tuple intents: (bet, number, "set", amount)
    """
    modes = spec.get("modes", {})
    mode = modes.get(mode_name) or {}
    tmpl = mode.get("template") or {}

    # Build state for expression evaluation: system first, then user/variables (user wins).
    state: Dict[str, Any] = {}
    state.update(getattr(vs, "system", {}) or {})
    user = getattr(vs, "user", None)
    if user is None:
        user = getattr(vs, "variables", {}) or {}
    state.update(user)

    bubble, table_level = _get_bubble_and_level(spec, vs)
    # templates.render_template requires (template, state, bubble, table_level)
    bets = render_template(tmpl, state, bubble, table_level)  # {bet_type: amount}

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
    Execute rules for an event and return tuple intents:
      (bet, number, action, amount)

    Behavior required by tests:
      • If rules match, execute each "do" statement in order:
          - variable mutations (e.g., "units += 10")
          - apply_template('ModeName') to emit tuple intents
      • If no rules match and event == "comeout", apply the active mode template once.
    """
    intents: List[Tuple] = []

    rules = spec.get("rules", [])
    matched: List[Dict[str, Any]] = []
    for rule in rules:
        cond = rule.get("on", {})
        if all(event.get(k) == v for k, v in cond.items()):
            matched.append(rule)

    def _active_mode_name() -> str:
        return (
            getattr(ctrl_state, "user", {}).get("mode")
            or getattr(ctrl_state, "variables", {}).get("mode")
            or next(iter(spec.get("modes", {}) or {"Main": {}}).keys())
        )

    def _apply_template(mode_name: str | None = None) -> None:
        name = mode_name or _active_mode_name()
        intents.extend(_template_to_intents(spec, ctrl_state, name))

    for rule in matched:
        for stmt in rule.get("do", []):
            s = stmt.strip()
            if s.startswith("apply_template"):
                # allow apply_template() or apply_template('Aggressive')
                rest = s.removeprefix("apply_template").strip()
                if rest.startswith("(") and rest.endswith(")"):
                    inner = rest[1:-1].strip()
                    if inner:
                        if (inner.startswith("'") and inner.endswith("'")) or (inner.startswith('"') and inner.endswith('"')):
                            inner = inner[1:-1]
                        _apply_template(inner)
                    else:
                        _apply_template(None)
                else:
                    _apply_template(None)
            else:
                # mutate ctrl_state.user if present else .variables
                state = getattr(ctrl_state, "user", None)
                if state is None:
                    state = getattr(ctrl_state, "variables", {})
                evaluate(s, state, event)

    if not matched and event.get("event") == "comeout":
        _apply_template(None)

    return intents