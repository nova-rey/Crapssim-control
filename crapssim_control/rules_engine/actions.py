"""
Action Catalog (v1) and Timing Guards for CSC Rules Engine.
Implements canonical verbs and legality validation.
"""

from typing import Any, Dict, Tuple


# --- Timing Guards -----------------------------------------------------------

def is_legal_timing(state: Dict[str, Any], action: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Enforce basic table-safe timing rules.
    Returns (legal: bool, reason: str)
    """
    if state.get("resolving"):
        return False, "during_resolution"
    if action["verb"] in {"switch_profile", "regress", "press_and_collect"}:
        # restrict some actions to come-out or post-resolution only
        if state.get("point_on") and state.get("roll_in_hand", 0) == 1:
            return False, "point_comeout_only"
    return True, "ok"


# --- Action Stubs ------------------------------------------------------------


class BaseAction:
    """Base stub for table-safe actions."""

    def __init__(self, name: str):
        self.name = name

    def execute(self, runtime: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
        """Stub execution — returns a trace entry only."""
        return {"applied": self.name, "args": args}


class SwitchProfile(BaseAction):
    """Switch active betting profile."""

    def execute(self, runtime, args):
        target = args.get("target") or args.get("profile") or "unknown"
        # stub: no actual runtime mutation
        return {"applied": "switch_profile", "target": target}


class Regress(BaseAction):
    """Reduce working bets by a pattern."""

    def execute(self, runtime, args):
        pattern = args.get("pattern") or "default"
        return {"applied": "regress", "pattern": pattern}


class PressAndCollect(BaseAction):
    """Press and collect pattern."""

    def execute(self, runtime, args):
        pattern = args.get("pattern") or "default"
        return {"applied": "press_and_collect", "pattern": pattern}


class Martingale(BaseAction):
    """Martingale progression step."""

    def execute(self, runtime, args):
        key = args.get("step_key")
        delta = args.get("delta", 1)
        max_level = args.get("max_level", 3)
        return {
            "applied": "martingale",
            "step_key": key,
            "delta": delta,
            "max_level": max_level,
        }


ACTIONS = {
    "switch_profile": SwitchProfile("switch_profile"),
    "regress": Regress("regress"),
    "press_and_collect": PressAndCollect("press_and_collect"),
    "martingale": Martingale("martingale"),
}
