from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any, Dict, List

_WHITELIST_VARS = {
    "bankroll","drawdown","profit",
    "hand_id","roll_in_hand","point_on","point_number","last_roll_total",
    "pso_count","box_hits","seed","run_id"
}
_WINDOWS = {"come_out_start","after_point_set","after_resolve","hand_end"}
_VERB_SIGS = {
    "switch_profile": {"name"},
    "press": {"bet","units"},
    "regress": {"bet","units"},
    "apply_policy": {"name"},
}

class DSLSpecError(Exception): pass

@dataclass
class RuleDef:
    id: str
    when: str
    then: str
    scope: str | None
    cooldown: Dict[str,int] | None
    guards: List[str]

def _validate_expr(expr: str) -> None:
    if "(" in expr or ")" in expr:
        # allow parentheses for precedence but no function calls
        # disallow patterns like name(  or )name
        if re.search(r"[A-Za-z_]\w*\s*\(", expr):
            raise DSLSpecError("Function calls not allowed in expressions")
    # forbid quotes to avoid strings
    if "'" in expr or '"' in expr:
        raise DSLSpecError("String literals not allowed")
    # variable names must be whitelisted
    for tok in re.findall(r"[A-Za-z_]\w*", expr):
        if tok in {"and","or","not","true","false"}: continue
        if tok not in _WHITELIST_VARS:
            raise DSLSpecError(f"Unknown variable in expression: {tok}")

def _parse_then(then: str) -> tuple[str, Dict[str, Any]]:
    m = re.match(r"\s*([a-z_]+)\s*\((.*)\)\s*$", then)
    if not m:
        raise DSLSpecError("then must be verb(args)")
    verb, args_src = m.group(1), m.group(2).strip()
    if verb not in _VERB_SIGS:
        raise DSLSpecError(f"Unknown verb: {verb}")
    args: Dict[str,Any] = {}
    if args_src:
        # very small parser: key=value, value numeric or bare identifier
        for part in [x.strip() for x in args_src.split(",") if x.strip()]:
            k,v = [p.strip() for p in part.split("=",1)]
            # numbers
            if re.fullmatch(r"-?\d+", v): args[k] = int(v)
            elif re.fullmatch(r"-?\d+\.\d+", v): args[k] = float(v)
            else:
                # bare identifier string like place_6 must be quoted in journaling
                args[k] = v.strip("'").strip('"')
    # check required keys if any
    req = _VERB_SIGS.get(verb, set())
    missing = [r for r in req if r not in args]
    if missing:
        raise DSLSpecError(f"Verb {verb} missing args: {missing}")
    return verb, args

def parse_rules(spec: Dict[str,Any]) -> List[RuleDef]:
    behavior = (spec or {}).get("behavior")
    if not behavior: return []
    if behavior.get("schema_version") != "1.0":
        raise DSLSpecError("behavior.schema_version must be '1.0'")
    rules = behavior.get("rules") or []
    out: List[RuleDef] = []
    for r in rules:
        rid = r.get("id")
        when = r.get("when")
        then = r.get("then")
        if not rid or not when or not then:
            raise DSLSpecError("Each rule requires id, when, then")
        _validate_expr(when)
        for g in r.get("guards", []) or []:
            _validate_expr(g)
        verb, args = _parse_then(then)
        scope = r.get("scope")  # "roll"|"hand"|"point_cycle"|None
        cd = r.get("cooldown")
        out.append(RuleDef(id=rid, when=when, then=f"{verb}", scope=scope, cooldown=cd, guards=r.get("guards") or []))
        # store args back for evaluator via an attached field
        out[-1].args = args  # type: ignore[attr-defined]
    return out
