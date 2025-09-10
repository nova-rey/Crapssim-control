from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
from .eval import safe_eval
from .templates import render_template
from .varstore import VarStore

BetIntent = Tuple[str, Optional[int], int]

def _match_on(on: Dict[str, Any], ev: Dict[str, Any]) -> bool:
    if not on:
        return False
    if on.get("event") != ev.get("event"):
        return False
    # All additional keys in 'on' must match exactly
    for k, v in on.items():
        if k == "event":
            continue
        if ev.get(k) != v:
            return False
    return True

def _do_assignment(vs: VarStore, stmt: str):
    stmt = stmt.strip()
    if "+=" in stmt:
        name, expr = stmt.split("+=", 1)
        vs.user[name.strip()] = vs.user.get(name.strip(), 0) + safe_eval(expr, vs.names())
        return
    if "-=" in stmt:
        name, expr = stmt.split("-=", 1)
        vs.user[name.strip()] = vs.user.get(name.strip(), 0) - safe_eval(expr, vs.names())
        return
    if "=" in stmt:
        name, expr = stmt.split("=", 1)
        vs.user[name.strip()] = safe_eval(expr, vs.names())
        return
    raise ValueError(f"Unsupported assignment: {stmt}")

def run_rules_for_event(spec: dict, vs: VarStore, event: Dict[str, Any]) -> List[BetIntent]:
    intents: List[BetIntent] = []
    rules: List[dict] = spec.get("rules", [])

    # Optional exposure of event name in expressions
    vs.user["_event"] = event.get("event")

    for rule in rules:
        on = rule.get("on", {})
        if not _match_on(on, event):
            continue

        cond = rule.get("if")
        if cond is not None and not bool(safe_eval(str(cond), vs.names())):
            continue

        for action in rule.get("do", []):
            action = str(action).strip()
            if action.startswith("apply_template"):
                inside = action[len("apply_template"):].strip()
                assert inside.startswith("(") and inside.endswith(")"), "apply_template must be like apply_template('Mode')"
                arg = inside[1:-1].strip()
                if arg.startswith("'") or arg.startswith('"'):
                    mode_name = arg.strip("'\"")
                else:
                    mode_name = str(vs.user.get(arg, arg))
                mode = spec.get("modes", {}).get(mode_name, {})
                tpl = mode.get("template", {})
                bubble = bool(vs.system.get("bubble", False))
                table_level = int(vs.system.get("table_level", 10))
                intents.extend(render_template(tpl, vs.names(), bubble=bubble, table_level=table_level))
            elif any(op in action for op in ("=", "+=", "-=")):
                _do_assignment(vs, action)
            elif action.startswith("log("):
                pass  # stub for future logging
            elif action == "clear_bets()":
                intents.append(("__clear__", None, 0))
            else:
                # Unknown action → ignore for now
                pass

    vs.user.pop("_event", None)
    return intents