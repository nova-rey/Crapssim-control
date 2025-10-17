from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .eval import evaluate
from .templates_legacy import render_template  # spec-time renderer


def _kind_number(bet_type: str) -> Tuple[str | None, int | None]:
    """
    Map template bet_type strings to the (bet, number) tuples expected by tests.
    Accept both 'pass' and 'pass_line' as Pass Line;
    map 'place_6' → ('place', 6), etc.
    """
    bt = bet_type.strip().lower()
    if bt in ("pass", "pass_line"):
        return ("pass", None)
    if bt.startswith("place_"):
        try:
            return ("place", int(bt.split("_", 1)[1]))
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
            table_level = int(tbl.get("table_level", tbl.get("level", 10)))

    return bool(bubble), int(table_level)


def _extract_amount(val: Any) -> float:
    """Accept raw number or {'amount': X}."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict) and "amount" in val:
        inner = val["amount"]
        if isinstance(inner, (int, float)):
            return float(inner)
        try:
            return float(inner)
        except Exception:
            return 0.0
    try:
        return float(val)
    except Exception:
        return 0.0


def _normalize_template_output_to_intents(bets_obj: Any) -> List[Tuple[str | None, int | None, str, float]]:
    """
    Accept either:
      • dict {bet_type: amount} OR {bet_type: {'amount': X}}
      • list/tuple of action dicts: [{"action":"set","bet_type":"pass","amount":10}, ...]
      • list/tuple of triplets: [("set","pass",10), ...]
    and return tuple intents: (bet, number, "set", amount)
    """
    intents: List[Tuple[str | None, int | None, str, float]] = []

    # dict form
    if isinstance(bets_obj, dict):
        for bet_type, amount in bets_obj.items():
            bet, number = _kind_number(str(bet_type))
            intents.append((bet, number, "set", _extract_amount(amount)))
        return intents

    # list/tuple form
    if isinstance(bets_obj, (list, tuple)):
        for item in bets_obj:
            # dict item
            if isinstance(item, dict):
                if item.get("action") != "set":
                    continue
                bt = item.get("bet_type")
                amt = _extract_amount(item.get("amount", 0.0))
                bet, number = _kind_number(str(bt))
                intents.append((bet, number, "set", amt))
                continue
            # tuple/list triplet
            if isinstance(item, (list, tuple)) and len(item) >= 3:
                action, bt, amt = item[0], item[1], _extract_amount(item[2])
                if action != "set":
                    continue
                bet, number = _kind_number(str(bt))
                intents.append((bet, number, "set", amt))
        return intents

    # Unknown type → nothing
    return intents


def _template_to_intents(spec: Dict[str, Any], vs: Any, mode_name: str) -> List[Tuple]:
    """
    Materialize the given mode's template into tuple intents: (bet, number, "set", amount)
    """
    modes = spec.get("modes", {})
    mode = modes.get(mode_name) or {}
    tmpl = mode.get("template") or {}

    # Build state for expression evaluation with correct precedence:
    # system + variables + user (user wins).
    state: Dict[str, Any] = {}
    state.update(getattr(vs, "system", {}) or {})
    state.update(getattr(vs, "variables", {}) or {})
    state.update(getattr(vs, "user", {}) or {})

    bubble, table_level = _get_bubble_and_level(spec, vs)

    # ---- Primary path: use the spec-time renderer (full fidelity) ----
    bets_obj = render_template(tmpl, state, bubble, table_level)
    intents = _normalize_template_output_to_intents(bets_obj)
    if intents:
        return intents

    # ---- Fallback path (important for simple/unit-test specs) ----
    # If the renderer produced nothing (e.g., minimal spec like {"pass": "units"}),
    # evaluate the short-form entries directly and convert to intents.
    fallback: Dict[str, float] = {}
    for k, v in (tmpl.items() if isinstance(tmpl, dict) else []):
        try:
            amt = evaluate(str(v), state)
        except Exception:
            amt = 0.0
        try:
            fallback[k] = float(amt)
        except Exception:
            # accept dicts like {"amount": X} in the short form too
            fallback[k] = _extract_amount(amt)

    return _normalize_template_output_to_intents(fallback)


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