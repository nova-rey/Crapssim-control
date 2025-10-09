from __future__ import annotations

from typing import Any, Dict, List, Optional

from .templates_rt import render_template as render_runtime_template, diff_bets
from .actions import make_action  # Action Envelope helper


class ControlStrategy:
    """
    Minimal, test-oriented controller.

    Provides:
      • point / rolls_since_point / on_comeout tracking
      • plan application on point_established (via runtime template) → diff to actions
      • regression after 3rd roll (clear place_6/place_8)
      • seven_out resets state
      • required adapter shims: update_bets(table) and after_roll(table, event)
    """

    def __init__(
        self,
        spec: Dict[str, Any],
        ctrl_state: Any | None = None,
        table_cfg: Optional[Dict[str, Any]] = None,
    ) -> None:
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

    @staticmethod
    def _extract_amount(val: Any) -> float:
        """
        Accept either a raw number or a dict like {'amount': 10}.
        Anything else coerces to 0.0 (defensive).
        """
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, dict) and "amount" in val:
            inner = val["amount"]
            if isinstance(inner, (int, float)):
                return float(inner)
            try:
                return float(inner)
            except Exception:
                return 0.0
        try:
            return float(val)
        except Exception:
            return 0.0

    @staticmethod
    def _normalize_plan(plan_obj: Any) -> List[Dict[str, Any]]:
        """
        Legacy normalizer retained for completeness; not used when diffing.
        Accepts:
          • dict {bet_type: amount} or {bet_type: {'amount': X}} → list of set dicts
          • list/tuple of dicts → pass through (amount normalized if present)
          • list/tuple of triplets → [('set','pass_line',10), ...] → dicts
        """
        out: List[Dict[str, Any]] = []

        if isinstance(plan_obj, dict):
            for bet_type, amount in plan_obj.items():
                out.append({
                    "action": "set",
                    "bet_type": str(bet_type),
                    "amount": ControlStrategy._extract_amount(amount),
                })
            return out

        if isinstance(plan_obj, (list, tuple)):
            for item in plan_obj:
                if isinstance(item, dict):
                    # normalize amount if present
                    if "amount" in item:
                        item = {**item, "amount": ControlStrategy._extract_amount(item["amount"])}
                    out.append(item)
                elif isinstance(item, (list, tuple)) and len(item) >= 3:
                    action, bet_type, amount = item[0], item[1], item[2]
                    out.append({
                        "action": str(action),
                        "bet_type": str(bet_type),
                        "amount": ControlStrategy._extract_amount(amount),
                    })
            return out

        return out

    def _apply_mode_template_plan(self, current_bets: Dict[str, Any], mode_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Render the active mode's template into a concrete desired_bets map,
        then compute a diff vs current_bets and return Action Envelopes stamped
        with source/id for provenance.
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

        desired = render_runtime_template(tmpl, st, event)
        # Produce standardized action envelopes with provenance + context note
        return diff_bets(
            current_bets or {},
            desired,
            source="template",
            source_id=f"template:{mode}",
            notes="template diff",
        )

    # ----- public API used by tests -----

    def handle_event(self, event: Dict[str, Any], current_bets: Dict[str, Any]) -> List[Dict[str, Any]]:
        ev_type = event.get("type")

        if ev_type == "comeout":
            self.point = None
            self.rolls_since_point = 0
            self.on_comeout = True
            return []

        if ev_type == "point_established":
            # Safer parsing of point value
            try:
                self.point = int(event.get("point"))
            except Exception:
                self.point = None
            self.rolls_since_point = 0
            self.on_comeout = self.point in (None, 0)
            return self._apply_mode_template_plan(current_bets, self.mode)

        if ev_type == "roll":
            if self.point:
                self.rolls_since_point += 1
                if self.rolls_since_point == 3:
                    # Regress: clear place_6 and place_8 with provenance
                    return [
                        make_action(
                            "clear",
                            bet_type="place_6",
                            source="template",
                            id_="template:regress_roll3",
                            notes="auto-regress after 3rd roll",
                        ),
                        make_action(
                            "clear",
                            bet_type="place_8",
                            source="template",
                            id_="template:regress_roll3",
                            notes="auto-regress after 3rd roll",
                        ),
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

    # ----- smoke-test shims expected by EngineAdapter -----

    def update_bets(self, table: Any) -> None:
        """Adapter calls this before each roll. No-op for tests."""
        return None

    def after_roll(self, table: Any, event: Dict[str, Any]) -> None:
        """
        Adapter calls this after each roll. For smoke tests we keep it minimal:
        - reset on seven_out
        """
        ev = event.get("event") or event.get("type")
        if ev == "seven_out":
            self.point = None
            self.rolls_since_point = 0
            self.on_comeout = True
        return None