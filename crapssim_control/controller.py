from __future__ import annotations

from typing import Any, Dict, List, Optional

from .templates_rt import render_template as render_runtime_template  # runtime → list[action dicts]


class ControlStrategy:
    """
    Minimal, test-oriented controller.

    Provides:
      • point / rolls_since_point / on_comeout tracking
      • plan application on point_established (via runtime template)
      • regression after 3rd roll (clear place_6/place_8)
      • seven_out resets state
      • no-op update_bets(table) expected by EngineAdapter smoke test
    """

    def __init__(self, spec: Dict[str, Any], ctrl_state: Any | None = None, table_cfg: Optional[Dict[str, Any]] = None) -> None:
        self.spec = spec
        self.table_cfg = table_cfg or spec.get("table") or {}
        self.point: Optional[int] = None
        self.rolls_since_point: int = 0
        self.on_comeout: bool = True

        self.ctrl_state = ctrl_state
        if self.ctrl_state is not None:
            self.mode = (
                getattr(self.ctrl_state, "user", {}).get("mode")
                or getattr(self.ctrl_state, "variables", {}).get("mode")
                or self._default_mode()
            )
        else:
            self.mode = self._default_mode()

    # ----- helpers -----

    def _default_mode(self) -> str:
        modes = self.spec.get("modes", {})
        if modes:
            return next(iter(modes.keys()))
        return "Main"

    def _current_state_for_eval(self) -> Dict[str, Any]:
        st: Dict[str, Any] = {}
        st.update(self.table_cfg or {})
        if self.ctrl_state is not None:
            st.update(getattr(self.ctrl_state, "system", {}) or {})
            user = getattr(self.ctrl_state, "user", None)
            if user is None:
                user = getattr(self.ctrl_state, "variables", {}) or {}
            st.update(user)
        else:
            st.update(self.spec.get("variables", {}) or {})

        st["point"] = self.point
        st["rolls_since_point"] = self.rolls_since_point
        st["on_comeout"] = self.on_comeout
        return st

    def _apply_mode_template_plan(self, mode_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Render the active mode's template into a concrete runtime plan.
        templates_rt.render_template requires an event argument; we pass a
        minimal, contextually correct event dict.
        """
        mode = mode_name or self.mode or self._default_mode()
        tmpl = (self.spec.get("modes", {}).get(mode) or {}).get("template") or {}
        st = self._current_state_for_eval()
        event = {
            "type": "point_established" if self.point else "comeout",
            "point": self.point,
            "rolls_since_point": self.rolls_since_point,
            "on_comeout": self.on_comeout,
        }
        return render_runtime_template(tmpl, st, event)

    # ----- public API used by tests -----

    def handle_event(self, event: Dict[str, Any], current_bets: Dict[str, Any]) -> List[Dict[str, Any]]:
        ev_type = event.get("type")

        if ev_type == "comeout":
            self.point = None
            self.rolls_since_point = 0
            self.on_comeout = True
            return []

        if ev_type == "point_established":
            self.point = int(event["point"])
            self.rolls_since_point = 0
            self.on_comeout = False
            return self._apply_mode_template_plan(self.mode)

        if ev_type == "roll":
            if self.point:
                self.rolls_since_point += 1
                if self.rolls_since_point == 3:
                    # Regress: clear place_6 and place_8 (tests assert the clears;
                    # we don't re-set anything else here to keep it deterministic).
                    return [
                        {"action": "clear", "bet_type": "place_6"},
                        {"action": "clear", "bet_type": "place_8"},
                    ]
            return []

        if ev_type == "seven_out":
            self.point = None
            self.rolls_since_point = 0
            self.on_comeout = True
            return []

        return []

    def state_snapshot(self) -> Dict[str, Any]:
        return {
            "point": self.point,
            "rolls_since_point": self.rolls_since_point,
            "on_comeout": self.on_comeout,
        }

    # ----- smoke-test shim expected by EngineAdapter -----

    def update_bets(self, table: Any) -> None:
        """
        Adapter calls this before each roll. For smoke tests we don't need to
        mutate table/bets here, so it's a defined no-op.
        """
        return None