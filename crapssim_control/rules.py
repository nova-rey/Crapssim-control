# crapssim_control/rules.py
from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
from .eval import safe_eval
from .templates import render_template
from .varstore import VarStore

BetIntent = Tuple[str, Optional[int], int]


def _match_on(on: Dict[str, Any], ev: Dict[str, Any]) -> bool:
    """All keys in 'on' must match the event dict."""
    if not on:
        return False
    if on.get("event") != ev.get("event"):
        return False
    for k, v in on.items():
        if k == "event":
            continue
        if ev.get(k) != v:
            return False
    return True


def _eval_expr(expr: str, vs: VarStore):
    """Evaluate an expression with whitespace tolerance."""
    return safe_eval(str(expr).strip(), vs.names())


def _do_assignment(vs: VarStore, stmt: str):
    """
    Support:
      name = expr
      name += expr
      name -= expr
    Whitespace is tolerated around operators.
    """
    s = stmt.strip()

    if "+=" in s:
        name, expr = s.split("+=", 1)
        key = name.strip()
        vs.user[key] = vs.user.get(key, 0) + _eval_expr(expr, vs)
        return

    if "-=" in s:
        name, expr = s.split("-=", 1)
        key = name.strip()
        vs.user[key] = vs.user.get(key, 0) - _eval_expr(expr, vs)
        return

    if "=" in s:
        name, expr = s.split("=", 1)
        key = name.strip()
        vs.user[key] = _eval_expr(expr, vs)
        return

    raise ValueError(f"Unsupported assignment: {stmt}")


def run_rules_for_event(spec: dict, vs: VarStore, event: Dict[str, Any]) -> List[BetIntent]:
    """
    Evaluate SPEC rules matching this event.
    Returns a list of BetIntent tuples to apply later.
    """
    intents: List[BetIntent] = []
    rules: List[dict] = spec.get("rules", [])

    # Expose event name for expressions if desired
    vs.user["_event"] = event.get("event")

    for rule in rules:
        on = rule.get("on", {})
        if not _match_on(on, event):
            continue

        cond = rule.get("if")
        if cond is not None and not bool(_eval_expr(str(cond), vs)):
            continue

        for action in rule.get("do", []):
            action = str(action).strip()

            if action.startswith("apply_template"):
                # apply_template('ModeName') or apply_template(modeVar)
                inside = action[len("apply_template"):].strip()
                if not (inside.startswith("(") and inside.endswith(")")):
                    raise AssertionError("apply_template must be like apply_template('Mode')")
                arg = inside[1:-1].strip()
                if (arg.startswith("'") and arg.endswith("'")) or (arg.startswith('"') and arg.endswith('"')):
                    mode_name = arg.strip("'\"")
                else:
                    # treat as variable name
                    mode_name = str(vs.user.get(arg, arg))

                mode = spec.get("modes", {}).get(mode_name, {})
                tpl = mode.get("template", {})
                bubble = bool(vs.system.get("bubble", False))
                table_level = int(vs.system.get("table_level", 10))
                intents.extend(render_template(tpl, vs.names(), bubble=bubble, table_level=table_level))

            elif any(op in action for op in ("=", "+=", "-=")):
                _do_assignment(vs, action)

            elif action.startswith("log("):
                # Stub for future logging sink
                pass

            elif action == "clear_bets()":
                # Sentinel handled by materializer
                intents.append(("__clear__", None, 0))

            else:
                # Unknown action → ignore for now
                pass

    vs.user.pop("_event", None)
    return intents