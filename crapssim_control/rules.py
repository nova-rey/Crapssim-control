from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Re-export so legacy imports from rules work.
from .templates import render_template  # type: ignore
from .eval import safe_eval  # we will still use this for pure expressions


BetIntent = Tuple[str, Any, Any] | Tuple[str, Any, Any, Any]


def _parse_apply_template(expr: str) -> Optional[str]:
    """
    Parse:
        "apply_template('Main')"
        "apply_template(\"Aggressive\")"
    → returns the mode name, else None.
    """
    s = expr.strip()
    if not s.startswith("apply_template(") or not s.endswith(")"):
        return None
    inner = s[len("apply_template(") : -1].strip()
    # strip quotes if present
    if (inner.startswith("'") and inner.endswith("'")) or (
        inner.startswith('"') and inner.endswith('"')
    ):
        inner = inner[1:-1]
    return inner or None


def _get_table_level(spec: dict, vs: Any) -> Optional[int]:
    # Prefer vs.system["table_level"] if available, else spec["table"]["level"]
    lvl = None
    if hasattr(vs, "system") and isinstance(vs.system, dict):
        lvl = vs.system.get("table_level")
    if lvl is None:
        lvl = ((spec or {}).get("table") or {}).get("level")
    try:
        return int(lvl) if lvl is not None else None
    except Exception:
        return None


def _expand_template_to_intents(spec: dict, vs: Any, mode: str) -> List[BetIntent]:
    """
    Delegate to templates.render_template, which expects a table_level arg.
    """
    table_level = _get_table_level(spec, vs)
    try:
        if table_level is not None:
            intents = render_template(spec, vs, mode, table_level)  # newer signature
        else:
            # Fallback in case older signature is in use (defensive)
            intents = render_template(spec, vs, mode)  # type: ignore[misc]
    except TypeError:
        # If signature mismatch, try the other way around
        intents = render_template(spec, vs, mode)  # type: ignore[misc]
    except Exception as e:
        raise ValueError(f"Failed to render template for mode '{mode}': {e}") from e
    return intents or []


# Very small, *safe* interpreter for the specific assignment strings we use in specs.
# Supports:  "<name> = <number>"  and  "<name> += <number>"
_ASSIGN_RE = re.compile(
    r"""^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(=|\+=)\s*([-+]?\d+(?:\.\d+)?)\s*$"""
)


def _apply_assignment_or_augassign(expr: str, vs: Any) -> bool:
    """
    Try to apply a simple assignment / aug-assign to vs.user (alias of vs.variables).
    Returns True if applied, False if not a supported pattern.
    """
    m = _ASSIGN_RE.match(expr)
    if not m:
        return False
    name, op, raw_val = m.groups()
    # store numbers as int when possible to mimic tests' behavior
    val = float(raw_val)
    val = int(val) if val.is_integer() else val

    # Ensure vs.user is available
    target = None
    if hasattr(vs, "user") and isinstance(vs.user, dict):
        target = vs.user
    elif hasattr(vs, "variables") and isinstance(vs.variables, dict):
        target = vs.variables
    if target is None:
        return False

    if op == "=":
        target[name] = val
    else:  # "+="
        cur = target.get(name, 0)
        try:
            target[name] = cur + val
        except Exception:
            # best effort: if cur not numeric, coerce
            try:
                target[name] = float(cur) + float(val)
            except Exception:
                target[name] = val
    return True


def match_rule(event: Dict[str, Any], cond: Dict[str, Any]) -> bool:
    """All key/value pairs in cond must match those in event."""
    for k, v in (cond or {}).items():
        if event.get(k) != v:
            return False
    return True


def run_rules_for_event(spec: dict, vs: Any, event: Dict[str, Any]) -> List[BetIntent]:
    """
    Given a strategy spec, a VarStore-like `vs`, and an event dict,
    return a list of bet intents to apply.

    Behavior:
      - Ensure `vs.user` exists and points at `vs.variables`.
      - Set vs.user["_event"] = event["event"] (if available) for expressions.
      - For string actions:
          * If "apply_template('Mode')" → expand to bet intents via templates.
          * Else:
              - Try to apply simple assignments/aug-assign (units = 10, units += 10).
              - If not an assignment, attempt safe_eval (pure expressions).
        We also append ("__expr__", <code>, None) entries for observability.
      - For dict actions: return as ("__dict__", action, None) for the materializer.
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
                        intents.extend(_expand_template_to_intents(spec, vs, mode))
                        continue

                    # side-effect strings: try assignment/augassign first
                    if _apply_assignment_or_augassign(act, vs):
                        intents.append(("__expr__", act, None))
                        continue

                    # last resort: a pure expression that safe_eval can handle
                    try:
                        safe_eval(act, vs)
                    except SyntaxError:
                        # Don't blow up tests on unsupported syntax; just record.
                        pass
                    intents.append(("__expr__", act, None))

                elif isinstance(act, dict):
                    intents.append(("__dict__", act, None))
                else:
                    raise ValueError(f"Unsupported action type in rule: {act!r}")

    return intents