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
    if action["verb"] in {"switch_profile", "regress", "press"}:
        # restrict some actions to come-out or post-resolution only
        if state.get("point_on") and state.get("roll_in_hand", 0) == 1:
            return False, "point_comeout_only"
    return True, "ok"


# --- Action Stubs ------------------------------------------------------------


class BaseAction:
    """Base stub for table-safe actions with adapter dispatch."""

    def __init__(self, name: str):
        self.name = name

    def _adapter(self, runtime: Dict[str, Any]):
        return runtime.get("adapter") if isinstance(runtime, dict) else None

    @staticmethod
    def _args(payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        inner = payload.get("args")
        if isinstance(inner, dict):
            return inner
        return payload if payload else {}

    def execute(self, runtime: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
        adapter = self._adapter(runtime)
        payload = self._args(args)
        if adapter and hasattr(adapter, "apply_action"):
            try:
                return adapter.apply_action(self.name, payload)
            except Exception:
                pass
        return {"verb": self.name, "args": payload, "result": "noop"}


class SwitchProfile(BaseAction):
    """Switch active betting profile."""

    def execute(self, runtime, args):
        payload = self._args(args)
        profile = payload.get("profile") or payload.get("target") or "default"
        adapter = self._adapter(runtime)
        if adapter and hasattr(adapter, "apply_action"):
            return adapter.apply_action("switch_profile", {"profile": profile})
        return {"verb": "switch_profile", "details": {"profile": profile}}


class Regress(BaseAction):
    """Reduce working bets by a pattern."""

    def execute(self, runtime, args):
        adapter = self._adapter(runtime)
        payload = self._args(args)
        if adapter and hasattr(adapter, "apply_action"):
            return adapter.apply_action("regress", payload)
        pattern = payload.get("pattern") or "default"
        return {"verb": "regress", "pattern": pattern}


class Press(BaseAction):
    """Increment a specific bet amount."""

    def execute(self, runtime, args):
        adapter = self._adapter(runtime)
        payload = self._args(args)
        if adapter and hasattr(adapter, "apply_action"):
            return adapter.apply_action("press", payload)
        target = (payload.get("target") or {}).get("bet")
        amount = (payload.get("amount") or {}).get("value")
        return {"verb": "press", "target": {"bet": target}, "amount": amount}


class SameBet(BaseAction):
    """Hold the current bet amount."""

    def execute(self, runtime, args):
        adapter = self._adapter(runtime)
        payload = self._args(args)
        if adapter and hasattr(adapter, "apply_action"):
            return adapter.apply_action("same_bet", payload)
        target = (payload.get("target") or {}).get("bet")
        return {"verb": "same_bet", "target": {"bet": target}}


class ApplyPolicy(BaseAction):
    """Apply a named policy through the adapter."""

    def execute(self, runtime, args):
        adapter = self._adapter(runtime)
        payload = self._args(args)
        if adapter and hasattr(adapter, "apply_action"):
            return adapter.apply_action("apply_policy", payload)
        return {"verb": "apply_policy", "policy": payload.get("policy")}


class Martingale(BaseAction):
    """Martingale progression step."""

    def execute(self, runtime, args):
        adapter = self._adapter(runtime)
        payload = self._args(args)
        if adapter and hasattr(adapter, "apply_action"):
            return adapter.apply_action("martingale", payload)
        key = payload.get("step_key")
        delta = payload.get("delta", 1)
        max_level = payload.get("max_level", 3)
        return {
            "verb": "martingale",
            "step_key": key,
            "delta": delta,
            "max_level": max_level,
        }


ACTIONS = {
    "switch_profile": SwitchProfile("switch_profile"),
    "regress": Regress("regress"),
    "press": Press("press"),
    "same_bet": SameBet("same_bet"),
    "apply_policy": ApplyPolicy("apply_policy"),
    "martingale": Martingale("martingale"),
}
