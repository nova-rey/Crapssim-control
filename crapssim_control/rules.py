from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
from .eval import safe_eval
from .templates import render_template
from .varstore import VarStore

# Actions are strings like:
#   "x = 5", "x += 1", "mode = 'Aggressive'", "apply_template('Aggressive')"

BetIntent = Tuple[str, Optional[int], int]

def _do_assignment(vs: VarStore, stmt: str):
    # handle simple forms: name = expr ; name += expr ; name -= expr
    stmt = stmt.strip()
    if "+=" in stmt:
        name, expr = stmt.split("+=", 1)
        name = name.strip()
        cur = vs.user.get(name, 0)
        val = safe_eval(expr, vs.names())
        vs.user[name] = cur + val
        return
    if "-=" in stmt:
        name, expr = stmt.split("-=", 1)
        name = name.strip()
        cur = vs.user.get(name, 0)
        val = safe_eval(expr, vs.names())
        vs.user[name] = cur - val
        return
    if "=" in stmt:
        name, expr = stmt.split("=", 1)
        name = name.strip()
        val = safe_eval(expr, vs.names())
        vs.user[name] = val
        return
    raise ValueError(f"Unsupported assignment: {stmt}")

def run_rules_for_event(spec: dict, vs: VarStore, event: Dict[str, Any]) -> List[BetIntent]:
    """
    Evaluate SPEC rules matching this event.
    Returns a list of BetIntent tuples to apply later.
    """
    intents: List[BetIntent] = []
    rules: List[dict] = spec.get("rules", [])
    # Expose a conventional "event" name to expressions if needed
    vs.user["_event"] = event.get("event")

    for rule in rules:
        on = rule.get("on", {})
        if on.get("event") != event.get("event"):
            continue

        cond = rule.get("if")
        if cond is not None:
            ok = bool(safe_eval(str(cond), vs.names()))
            if not ok:
                continue

        for action in rule.get("do", []):
            action = str(action).strip()
            if action.startswith("apply_template"):
                # Parse apply_template('ModeName') or apply_template(mode)
                inside = action[len("apply_template"):].strip()
                assert inside.startswith("(") and inside.endswith(")"), "apply_template must be like apply_template('Mode')"
                arg = inside[1:-1].strip()
                if arg.startswith("'") or arg.startswith('"'):
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
                # no-op placeholder; you can print or collect logs later
                pass
            elif action == "clear_bets()":
                # we’ll implement clearing in the materializer step; for now emit a sentinel
                intents.append(("__clear__", None, 0))
            else:
                # Unknown action → ignore or raise (for now, ignore)
                pass

    # Cleanup transient
    vs.user.pop("_event", None)
    return intents