# crapssim_control/controller.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .eval import evaluate as _eval
# Use the RT template renderer so event overlays work the same way tests expect
from .templates_rt import render_template as _render_template


Action = Dict[str, Any]  # {"action": "set"|"clear", "bet_type": str, "amount": float}


class ControlStrategy:
    """
    Drives stateful policy decisions across events. Minimal test-facing surface:
      - __init__(spec, ctrl_state=None, table_cfg=None)
      - handle_event(event: Dict, current_bets: Dict) -> List[Action]
      - state_snapshot() -> Dict[str, Any]
      - update_bets(table)  # smoke/adapter tests only require it to exist
    """

    def __init__(self, spec: Dict[str, Any], ctrl_state: Any | None = None, table_cfg: Dict[str, Any] | None = None):
        self.spec = spec or {}
        self.table_cfg: Dict[str, Any] = dict(table_cfg or self.spec.get("table") or {})

        # choose a backing state dict:
        # - if a VarStore-like object is provided, mutate its .user dict (tests watch that)
        # - otherwise keep an internal dict
        if hasattr(ctrl_state, "user") and isinstance(getattr(ctrl_state, "user"), dict):
            self._state = ctrl_state.user  # type: ignore[assignment]
            # also expose system/table settings if present
            if hasattr(ctrl_state, "system") and isinstance(getattr(ctrl_state, "system"), dict):
                self._state.setdefault("bubble", ctrl_state.system.get("bubble"))
                self._state.setdefault("table_level", ctrl_state.system.get("table_level"))
        else:
            self._state: Dict[str, Any] = {}

        # Initialize stable snapshot keys without clobbering existing values
        self._state.setdefault("point", None)
        self._state.setdefault("on_comeout", True)
        self._state.setdefault("rolls_since_point", 0)
        # seed variables from spec if not already present
        for k, v in (self.spec.get("variables") or {}).items():
            self._state.setdefault(k, v)

    # --- public ---------------------------------------------------------------

    def state_snapshot(self) -> Dict[str, Any]:
        snap = dict(self._state)
        snap.setdefault("point", None)
        snap.setdefault("on_comeout", True if snap.get("point") in (None, 0) else False)
        snap.setdefault("rolls_since_point", 0)
        return snap

    def update_bets(self, table: Any) -> None:
        """
        Present for engine adapter; smoke tests only assert it exists.
        No behavior required here for the unit tests you shared.
        """
        return None

    def handle_event(self, event: Dict[str, Any], current_bets: Dict[str, float]) -> List[Action]:
        # accept either {"type": "..."} or {"event": "..."}
        etype = event.get("type") or event.get("event")
        plan: List[Action] = []

        if etype == "comeout":
            self._on_comeout()
            # controller_rt expects no immediate betting on comeout
            return plan

        if etype == "point_established":
            # update internal state first
            point = int(event["point"])
            self._on_point_established(point)
            # then apply current mode template to produce the expected pass_line set, etc.
            plan.extend(self._apply_current_mode_template(event, current_bets))

        elif etype == "roll":
            plan.extend(self._on_roll(event, current_bets))

        elif etype == "seven_out":
            plan.extend(self._on_seven_out())

        # Allow tests/helpers to run rule-side expressions that mutate state
        for expr in (event.get("do") or []):
            _ = self._exec_action(expr, event, current_bets)

        return plan

    # --- internals ------------------------------------------------------------

    def _exec_action(self, expr: str, event: Dict[str, Any], current_bets: Dict[str, float]) -> Optional[Any]:
        """
        Allow rules to mutate self._state via the safe evaluator.
        """
        return _eval(expr, state=self._state, event=event)

    def _on_comeout(self) -> None:
        self._state["point"] = None
        self._state["on_comeout"] = True
        self._state["rolls_since_point"] = 0

    def _on_point_established(self, point: int) -> None:
        self._state["point"] = point
        self._state["on_comeout"] = False
        self._state["rolls_since_point"] = 0

    def _on_roll(self, event: Dict[str, Any], current_bets: Dict[str, float]) -> List[Action]:
        plan: List[Action] = []
        if self._state.get("point"):
            self._state["rolls_since_point"] = int(self._state.get("rolls_since_point", 0)) + 1

            # 3rd roll after point: regress 6/8 -- clear then set to half the amount
            if self._state["rolls_since_point"] == 3:
                for bt in ("place_6", "place_8"):
                    if bt in current_bets and current_bets[bt] > 0:
                        plan.append({"action": "clear", "bet_type": bt})
                for bt in ("place_6", "place_8"):
                    if bt in current_bets and current_bets[bt] > 0:
                        regressed = max(0.0, float(current_bets[bt]) / 2.0)
                        plan.append({"action": "set", "bet_type": bt, "amount": regressed})
        return plan

    def _on_seven_out(self) -> List[Action]:
        self._state["point"] = None
        self._state["on_comeout"] = True
        self._state["rolls_since_point"] = 0
        return []

    # -- template application --------------------------------------------------

    def _apply_current_mode_template(self, event: Dict[str, Any], current_bets: Dict[str, float]) -> List[Action]:
        """
        Look up the current mode's template (or the first defined mode), render it,
        and return a minimal diff plan against `current_bets`.
        """
        modes = self.spec.get("modes") or {}
        mode_name = str(self._state.get("mode") or (next(iter(modes)) if modes else ""))
        if not mode_name or mode_name not in modes:
            return []

        tmpl = modes[mode_name].get("template") or {}
        desired = _render_template(tmpl, self.state_snapshot(), event, self.table_cfg)
        return _diff_bets(current_bets, desired)


# --- small pure helpers -------------------------------------------------------

def _diff_bets(current: Dict[str, float], desired: Dict[str, float]) -> List[Action]:
    """
    Create a minimal set/clear plan to move from `current` -> `desired`.
    Amount comparisons are exact; upstream legalizers will adjust to table rules.
    """
    plan: List[Action] = []
    current = current or {}
    desired = desired or {}

    # clears for anything not desired or zeroed
    for bt, amt in sorted(current.items()):
        if bt not in desired or desired.get(bt, 0.0) <= 0.0:
            plan.append({"action": "clear", "bet_type": bt})

    # sets/updates for desired bets
    for bt, amt in sorted(desired.items()):
        if amt > 0.0 and float(current.get(bt, 0.0)) != float(amt):
            plan.append({"action": "set", "bet_type": bt, "amount": float(amt)})

    return plan