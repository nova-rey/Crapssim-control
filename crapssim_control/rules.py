# crapssim_control/rules.py
from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
from .eval import safe_eval
from .templates import render_template
from .varstore import VarStore

# BetIntent now allows meta dict as 4th element
BetIntent = Tuple[str, Optional[int], int, Dict[str, Any]]

def _match_on(on: Dict[str, Any], ev: Dict[str, Any]) -> bool:
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
    return safe_eval(str(expr).strip(), vs.names())

def _do_assignment(vs: VarStore, stmt: str):
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

def _parse_call(action: str, fname: str) -> Optional[str]:
    """Return inside of parentheses if action startswith fname(...)."""
    if not action.startswith(fname):
        return None
    inside = action[len(fname):].strip()
    if not (inside.startswith("(") and inside.endswith(")")):
        raise AssertionError(f"{fname} must be like {fname}('arg1', ...)")
    return inside[1:-1].strip()

def _parse_apply_template_arg(arg: str, vs: VarStore) -> str:
    # accept 'Mode' or a variable name
    if (arg.startswith("'") and arg.endswith("'")) or (arg.startswith('"') and arg.endswith('"')):
        return arg.strip("'\"")
    return str(vs.user.get(arg, arg))

def _parse_apply_odds_args(inner: str, vs: VarStore) -> tuple[str, int, str]:
    """
    Parse apply_odds(kind, expr, scope='all'|'newest')
    - kind: 'come' | 'dont_come'
    - expr: arithmetic expression (evaluated)
    - scope: optional, default 'all'
    """
    # naive split that respects commas in quotes minimally
    parts: List[str] = []
    depth = 0
    buf = []
    for ch in inner:
        if ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
            continue
        if ch in "'\"":
            depth = 1 - depth  # toggle
        buf.append(ch)
    if buf:
        parts.append("".join(buf).strip())

    if len(parts) < 2:
        raise AssertionError("apply_odds(kind, expr[, scope]) requires at least 2 args")

    raw_kind = parts[0].strip()
    if (raw_kind.startswith("'") and raw_kind.endswith("'")) or (raw_kind.startswith('"') and raw_kind.endswith('"')):
        kind = raw_kind.strip("'\"")
    else:
        kind = str(vs.user.get(raw_kind, raw_kind))

    expr = parts[1]
    desired = int(_eval_expr(expr, vs))

    scope = "all"
    if len(parts) >= 3:
        raw_scope = parts[2].strip()
        if raw_scope.startswith("scope="):
            raw_scope = raw_scope.split("=", 1)[1].strip()
        if (raw_scope.startswith("'") and raw_scope.endswith("'")) or (raw_scope.startswith('"') and raw_scope.endswith('"')):
            scope = raw_scope.strip("'\"")
        else:
            scope = str(vs.user.get(raw_scope, raw_scope))

    if kind not in ("come", "dont_come"):
        raise AssertionError("apply_odds kind must be 'come' or 'dont_come'")
    if scope not in ("all", "newest"):
        raise AssertionError("apply_odds scope must be 'all' or 'newest'")

    return kind, desired, scope

def run_rules_for_event(spec: dict, vs: VarStore, event: Dict[str, Any]) -> List[BetIntent]:
    intents: List[BetIntent] = []
    rules: List[dict] = spec.get("rules", [])
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

            # apply_template('ModeName' | var)
            inner = _parse_call(action, "apply_template")
            if inner is not None:
                arg = inner
                mode_name = _parse_apply_template_arg(arg, vs)
                mode = spec.get("modes", {}).get(mode_name, {})
                tpl = mode.get("template", {})
                bubble = bool(vs.system.get("bubble", False))
                table_level = int(vs.system.get("table_level", 10))
                intents.extend(render_template(tpl, vs.names(), bubble=bubble, table_level=table_level))
                continue

            # apply_odds('come'|'dont_come', expr [, scope='all'|'newest'])
            inner = _parse_call(action, "apply_odds")
            if inner is not None:
                kind, desired, scope = _parse_apply_odds_args(inner, vs)
                intents.append(("__apply_odds__", kind, int(desired), {"scope": scope}))
                continue

            # simple assignments
            if any(op in action for op in ("=", "+=", "-=")):
                _do_assignment(vs, action)
                continue

            if action.startswith("log("):
                # placeholder: logging is handled by controller if needed
                continue

            if action == "clear_bets()":
                intents.append(("__clear__", None, 0, {}))
                continue

            # Unknown action: ignore for forward compatibility

    vs.user.pop("_event", None)
    return intents