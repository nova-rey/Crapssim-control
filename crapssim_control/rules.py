# ---- compatibility shim for legacy import path (rules.render_template) ----
from typing import Any, Dict, List, Optional, Tuple

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
# crapssim_control/rules.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import re

BetIntent = Tuple[str, ...]  # ("place", "pass", "units"), ("__clear__",), etc.


# ---------- helpers ----------

def _coerce_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _eval_expr(expr: str, env: Dict[str, Any]) -> Any:
    # VERY restricted eval environment (tests use simple math / var refs)
    allowed_builtins = {"min": min, "max": max, "round": round, "int": int, "abs": abs}
    return eval(expr, {"__builtins__": allowed_builtins}, env)


def _render_apply_template(spec: dict, vs, intents: List[BetIntent]) -> None:
    # Rules can push "apply_template('Mode')" into intents. We keep it symbolic here;
    # controller.render_template(...) will materialize it.
    pass


# ---------- public API ----------

def run_rules_for_event(spec: dict, vs, event: Dict[str, Any]) -> List[BetIntent]:
    """
    Interpret rules for a given event. Produces a list of BetIntent tuples.
    Does NOT mutate the table/player; that’s left to materialize.apply_intents().
    """
    intents: List[BetIntent] = []
    rules: List[dict] = spec.get("rules", [])

    # Do NOT assume vs.user exists; use a temp overlay.
    # (Some strategies/tests may inspect this during expression eval.)
    user_overlay: Dict[str, Any] = {}
    user_overlay["_event"] = event.get("event")

    # Build the expression/assignment environment.
    env = {
        # variables
        **getattr(vs, "variables", {}),
        # system values (e.g., table_level, comeout flags some tests inject)
        **getattr(vs, "system", {}),
        # counters (if present)
        **getattr(vs, "counters", {}),
        # ephemeral event values
        **event,
        # user overlay for ad-hoc flags
        "_user": user_overlay,
    }

    # --- match & execute rules ---
    for rule in rules:
        on: Dict[str, Any] = rule.get("on", {})
        # All keys in 'on' must match env (simple equality)
        matched = True
        for k, v in on.items():
            if env.get(k) != v:
                matched = False
                break
        if not matched:
            continue

        actions = rule.get("do", [])
        for act in actions:
            if not isinstance(act, str):
                continue

            # apply_template('Mode')
            if act.startswith("apply_template("):
                intents.append(("__template__", act))
                continue

            # clear bets sentinel
            if act.strip() == "clear_bets()":
                intents.append(("__clear__",))
                continue

            # odds application sentinel
            if act.strip() == "apply_odds()":
                intents.append(("__apply_odds__",))
                continue

            # assignment / arithmetic like: units += 10, units = 5, etc.
            # mutate vs.variables (tests rely on this)
            m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*([+\-*/%]?=)\s*(.+?)\s*$", act)
            if m:
                name, op, rhs = m.groups()
                # ensure the target is in variables bag
                if name not in vs.variables:
                    vs.variables[name] = env.get(name, 0)
                # compute RHS
                rhs_val = _eval_expr(rhs, env)
                if op == "=":
                    vs.variables[name] = rhs_val
                elif op == "+=":
                    vs.variables[name] = _coerce_int(vs.variables[name]) + _coerce_int(rhs_val)
                elif op == "-=":
                    vs.variables[name] = _coerce_int(vs.variables[name]) - _coerce_int(rhs_val)
                elif op == "*=":
                    vs.variables[name] = _coerce_int(vs.variables[name]) * _coerce_int(rhs_val)
                elif op == "/=":
                    denom = _coerce_int(rhs_val, 1) or 1
                    vs.variables[name] = _coerce_int(vs.variables[name]) // denom
                # refresh env for subsequent actions
                env[name] = vs.variables[name]
                continue

            # Fallback: push through as a raw intent string (e.g., "place('field', units)")
            intents.append(("__raw__", act))

    return intents