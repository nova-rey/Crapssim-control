"""
templates_rt.py -- Batch 14 (Runtime Templates)

Render a strategy "template" (with expressions) into desired bets,
then diff against current bets to produce a deterministic action plan.

Schema (flexible, minimal v0):

template = {
  "pass": "units",                         # pass line
  "dont_pass": 0,                          # clear / not present
  "field": "units/2",
  "place": { "6": "units*2", "8": "units*2", "5": "units" },
  "odds": { "pass": "units*2" },          # when point is on
  "working_on_comeout": False             # default odds working flag (can be overridden per action)
}

current_bets = {
  "pass_line": {"amount": 10},
  "place_6": {"amount": 12},
  ...
}

Outputs:
  - render_template(...) -> desired_bets  (same shape as current_bets)
  - diff_bets(current_bets, desired_bets) -> list[actions]
      actions are:
        {"action":"set", "bet_type":"place_6", "amount":12}
        {"action":"clear","bet_type":"field"}
        {"action":"set","bet_type":"odds_6_pass","amount":20,"working_on_comeout":False}
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Any

from .eval import eval_num, EvalError
from .legalize_rt import legalize_amount


def _bool(x: Any, default: bool = False) -> bool:
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return bool(x)
    if isinstance(x, str):
        s = x.strip().lower()
        if s in ("true", "t", "1", "yes", "y", "on"):
            return True
        if s in ("false", "f", "0", "no", "n", "off"):
            return False
    return default


def _cfg(table_cfg: Optional[Dict]) -> Dict:
    cfg = {
        "bubble": False,
        "level": 10,
        "place_410_increment": 5,
        "max_odds_multiple": 3.0,
    }
    if table_cfg:
        cfg.update(table_cfg)
    return cfg


def _eval_amount(expr_or_num: Any, state: Dict, event: Dict) -> float:
    if isinstance(expr_or_num, (int, float)):
        return float(expr_or_num)
    if expr_or_num is None:
        return 0.0
    if isinstance(expr_or_num, str):
        return float(eval_num(expr_or_num, state, event))
    # unknown types → zero (effectively "clear")
    return 0.0


def render_template(
    template: Dict,
    state: Dict,
    event: Dict,
    table_cfg: Optional[Dict] = None,
) -> Dict[str, Dict]:
    """
    Evaluate a template into canonical desired_bets (already legalized).
    """
    cfg = _cfg(table_cfg or {})
    desired: Dict[str, Dict[str, Any]] = {}
    point = event.get("point") or state.get("point")
    on_comeout = bool(event.get("on_comeout", state.get("on_comeout", False)))

    # ---- Line bets
    if "pass" in template:
        amt = _eval_amount(template.get("pass"), state, event)
        legal, _ = legalize_amount("pass_line", amt, cfg)
        if legal > 0:
            desired["pass_line"] = {"amount": legal}

    if "dont_pass" in template:
        amt = _eval_amount(template.get("dont_pass"), state, event)
        legal, _ = legalize_amount("dont_pass", amt, cfg)
        if legal > 0:
            desired["dont_pass"] = {"amount": legal}

    if "field" in template:
        amt = _eval_amount(template.get("field"), state, event)
        legal, _ = legalize_amount("field", amt, cfg)
        if legal > 0:
            desired["field"] = {"amount": legal}

    # ---- Place bets
    place = template.get("place")
    if isinstance(place, dict):
        for num_str, expr in place.items():
            try:
                num = int(num_str)
            except Exception:
                continue
            raw = _eval_amount(expr, state, event)
            legal, _ = legalize_amount(f"place_{num}", raw, cfg, point=point)
            if legal > 0:
                desired[f"place_{num}"] = {"amount": legal}

    # ---- Odds (only when a point is on)
    if point:
        odds = template.get("odds")
        if isinstance(odds, dict):
            # support odds on pass or don't separately (start with pass)
            base_pass = desired.get("pass_line", {}).get("amount", 0)
            base_dp = desired.get("dont_pass", {}).get("amount", 0)

            if "pass" in odds and base_pass > 0:
                raw = _eval_amount(odds["pass"], state, event)
                legal, flags = legalize_amount(
                    f"odds_{int(point)}_pass",
                    raw,
                    cfg,
                    point=point,
                    base_line_bet=base_pass,
                )
                if legal > 0:
                    desired[f"odds_{int(point)}_pass"] = {"amount": legal}

            if "dont" in odds and base_dp > 0:
                raw = _eval_amount(odds["dont"], state, event)
                legal, flags = legalize_amount(
                    f"odds_{int(point)}_dont",
                    raw,
                    cfg,
                    point=point,
                    base_line_bet=base_dp,
                )
                if legal > 0:
                    desired[f"odds_{int(point)}_dont"] = {"amount": legal}

    # ---- Working flag for odds on comeout (optional)
    working_flag = _bool(template.get("working_on_comeout", False), False)
    if working_flag and on_comeout:
        # annotate any odds entries with explicit working flag
        for k, v in desired.items():
            if k.startswith("odds_"):
                v["working_on_comeout"] = True

    return desired


def diff_bets(current_bets: Dict[str, Dict], desired_bets: Dict[str, Dict]) -> List[Dict]:
    """
    Compute idempotent actions to reconcile from current -> desired.

    - If desired has bet with amount A:
        - if current missing or amount != A -> "set" to A
    - If current has bet that's absent in desired -> "clear"
    - Amount <= 0 is treated as absent
    """
    actions: List[Dict] = []

    # Normalize to simple amount maps
    def _amt(dct: Optional[Dict]) -> int:
        if not dct:
            return 0
        try:
            return int(dct.get("amount", 0))
        except Exception:
            return 0

    current = {k: _amt(v) for k, v in (current_bets or {}).items()}
    desired = {k: _amt(v) for k, v in (desired_bets or {}).items()}

    # set / update
    for k, amt in desired.items():
        if amt > 0 and current.get(k) != amt:
            action = {"action": "set", "bet_type": k, "amount": amt}
            # pass through working flag if present
            wf = (desired_bets.get(k) or {}).get("working_on_comeout")
            if isinstance(wf, bool):
                action["working_on_comeout"] = wf
            actions.append(action)

    # clear
    for k, amt in current.items():
        if k not in desired or desired.get(k, 0) <= 0:
            actions.append({"action": "clear", "bet_type": k})

    # Stable ordering (deterministic): clears first (alpha), then sets (alpha)
    clears = [a for a in actions if a["action"] == "clear"]
    sets = [a for a in actions if a["action"] == "set"]
    actions = sorted(clears, key=lambda a: a["bet_type"]) + sorted(sets, key=lambda a: a["bet_type"])
    return actions