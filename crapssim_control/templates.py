from typing import Dict, Any, List, Tuple, Optional
from .legalize import legalize_amount
from .eval import safe_eval

BetIntent = Tuple[str, Optional[int], int]  # (kind, number, amount)

def _eval_amount(x, vars_map: Dict[str, Any]) -> int:
    if isinstance(x, (int, float)):
        return int(x)
    return int(safe_eval(str(x), vars_map))

def render_template(template: Dict[str, Any], vars_map: Dict[str, Any], bubble: bool, table_level: int) -> List[BetIntent]:
    """
    Convert a template dict into a list of bet intents with legalized amounts.
    Supported keys:
      - "pass", "dont_pass", "field": scalar amount (expr or number)
      - "place": { "6": expr, "8": expr, ... }
    """
    out: List[BetIntent] = []

    if "pass" in template:
        amt = legalize_amount(None, _eval_amount(template["pass"], vars_map), bubble, table_level)
        out.append(("pass", None, amt))
    if "dont_pass" in template:
        amt = legalize_amount(None, _eval_amount(template["dont_pass"], vars_map), bubble, table_level)
        out.append(("dont_pass", None, amt))
    if "field" in template:
        amt = legalize_amount(None, _eval_amount(template["field"], vars_map), bubble, table_level)
        out.append(("field", None, amt))
    if "place" in template:
        for k, v in template["place"].items():
            n = int(k)
            amt = legalize_amount(n, _eval_amount(v, vars_map), bubble, table_level)
            out.append(("place", n, amt))

    return out