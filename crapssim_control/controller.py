# crapssim_control/controller.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .templates_rt import render_template as render_runtime_template, diff_bets
from .actions import make_action  # Action Envelope helper
from .rules_rt import apply_rules  # Runtime rules engine
from .csv_journal import CSVJournal  # Per-event journaling
from .events import canonicalize_event, COMEOUT, POINT_ESTABLISHED, ROLL, SEVEN_OUT


class ControlStrategy:
    """
    Minimal, test-oriented controller.

    Provides:
      • point / rolls_since_point / on_comeout tracking
      • plan application on point_established (via runtime template) → diff to actions
      • regression after 3rd roll (clear place_6/place_8)
      • rules engine (MVP) called on every event and merged after template/regression
      • per-event CSV journaling (when enabled via spec.run.csv)
      • required adapter shims: update_bets(table) and after_roll(table, event)

    P4C2 upgrades:
      • Canonicalize all inbound events via events.canonicalize_event(...)
      • Stable event fields for rules ('type', 'roll', 'point', 'on_comeout', ...)
      • Snapshot/journaling now includes canonical event fields where useful
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

        # Journaling: lazy-init on first use
        self._journal: Optional[CSVJournal] = None
        self._journal_enabled: Optional[bool] = None  # tri-state: None unknown, True/False decided

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
        st["mode"] = getattr(self, "mode", None)
        return st

    def _units_from_spec_or_state(self) -> Optional[float]:
        # Prefer ctrl_state variables if present; else spec.variables
        val = None
        if self.ctrl_state is not None:
            v = getattr(self.ctrl_state, "user", None)
            if v is None:
                v = getattr(self.ctrl_state, "variables", {}) or {}
            val = (v or {}).get("units")
        if val is None:
            val = (self.spec.get("variables", {}) or {}).get("units")
        try:
            return float(val) if val is not None else None
        except Exception:
            return None

    def _bankroll_best_effort(self) -> Optional[float]:
        """
        Best-effort bankroll hint for CSV context (optional).
        We avoid importing engine objects; look for hints in spec.run/table.
        """
        run = self.spec.get("run", {}) or {}
        table = self.spec.get("table", {}) or {}
        for k in ("bankroll", "starting_bankroll"):
            v = run.get(k)
            if v is None:
                v = table.get(k)
            if v is not None:
                try:
                    return float(v)
                except Exception:
                    pass
        return None

    def _resolve_journal_cfg(self) -> Optional[Dict[str, Any]]:
        """
        Read journaling config from spec["run"]["csv"].
        Returns a dict with normalized keys or None if disabled/missing.
        """
        run = self.spec.get("run", {}) if isinstance(self.spec, dict) else {}
        csv_cfg = run.get("csv") if isinstance(run, dict) else None
        if not isinstance(csv_cfg, dict):
            return None
        enabled = bool(csv_cfg.get("enabled", False))
        path = csv_cfg.get("path")
        if not enabled or not path:
            return None
        append = True if csv_cfg.get("append", True) not in (False, "false", "no", 0) else False
        run_id = csv_cfg.get("run_id")  # optional
        seed = csv_cfg.get("seed")      # optional
        try:
            seed_val = int(seed) if seed is not None else None
        except Exception:
            seed_val = None
        return {"path": str(path), "append": append, "run_id": run_id, "seed": seed_val}

    def _ensure_journal(self) -> Optional[CSVJournal]:
        """
        Lazy-create CSVJournal if enabled in spec.run.csv. Cache enable/disable decision.
        Never raises; on failure we disable journaling for the session.
        """
        if self._journal_enabled is False:
            return None
        if self._journal is not None:
            self._journal_enabled = True
            return self._journal

        cfg = self._resolve_journal_cfg()
        if not cfg:
            self._journal_enabled = False
            return None

        try:
            j = CSVJournal(cfg["path"], append=cfg["append"], run_id=cfg.get("run_id"), seed=cfg.get("seed"))
            # Do not write header here; writer will handle on first write.
            self._journal = j
            self._journal_enabled = True
            return j
        except Exception:
            # Disable if we cannot construct (e.g., bad path)
            self._journal_enabled = False
            self._journal = None
            return None

    def _snapshot_for_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build a compact snapshot for CSV rows. Only simple, stable fields.
        """
        snap = {
            "event_type": event.get("type"),
            "point": self.point,
            "rolls_since_point": self.rolls_since_point,
            "on_comeout": self.on_comeout,
            "mode": getattr(self, "mode", None),
            "units": self._units_from_spec_or_state(),
            "bankroll": self._bankroll_best_effort(),
            # Optional: include canonical roll/point for convenience
            "roll": event.get("roll"),
            "event_point": event.get("point"),
        }
        return snap

    def _journal_actions(self, event: Dict[str, Any], actions: List[Dict[str, Any]]) -> None:
        """
        Best-effort: write action envelopes to CSV if journaling is enabled.
        Never raises; failures silently disable journaling for the rest of the run.
        """
        if not actions:
            return
        j = self._ensure_journal()
        if j is None:
            return
        try:
            j.write_actions(actions, snapshot=self._snapshot_for_event(event))
        except Exception:
            # One strike policy: disable on first failure to avoid spam
            self._journal_enabled = False
            self._journal = None

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

        # Synthesize a minimal canonical event representing table posture for templates
        synth_event = canonicalize_event({
            "type": POINT_ESTABLISHED if self.point else COMEOUT,
            "point": self.point,
            "on_comeout": self.on_comeout,
        })

        desired = render_runtime_template(tmpl, st, synth_event)
        # Produce standardized action envelopes with provenance + context note
        return diff_bets(
            current_bets or {},
            desired,
            source="template",
            source_id=f"template:{mode}",
            notes="template diff",
        )

    def _apply_rules_for_event(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Run rules engine for this canonical event and return envelopes."""
        rules = self.spec.get("rules") if isinstance(self.spec, dict) else None
        st = self._current_state_for_eval()
        # apply_rules is permissive (returns [] on bad input); never raises
        return apply_rules(rules, st, event or {})

    # ----- public API used by tests -----

    def handle_event(self, event: Dict[str, Any], current_bets: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Produce a list of Action Envelopes for the given event by:
          1) canonicalizing and updating internal state,
          2) generating template diff/regression actions,
          3) appending rule-driven actions,
          4) journaling envelopes to CSV if enabled.
        """
        # Normalize inbound event to the canonical contract
        event = canonicalize_event(event or {})
        ev_type = event.get("type")

        # Aggregate actions per event (template/regression first; rules appended after)
        actions: List[Dict[str, Any]] = []

        if ev_type == COMEOUT:
            # Update state
            self.point = None
            self.rolls_since_point = 0
            self.on_comeout = True
            # No template plan on pure comeout; just run rules for comeout
            actions.extend(self._apply_rules_for_event(event))
            # Journal and return
            self._journal_actions(event, actions)
            return actions

        if ev_type == POINT_ESTABLISHED:
            # Safer parsing of point value
            try:
                self.point = int(event.get("point"))
            except Exception:
                self.point = None
            self.rolls_since_point = 0
            self.on_comeout = self.point in (None, 0)

            # 1) Template diff actions for this mode
            actions.extend(self._apply_mode_template_plan(current_bets, self.mode))
            # 2) Rule actions (appended)
            actions.extend(self._apply_rules_for_event(event))
            # Journal and return
            self._journal_actions(event, actions)
            return actions

        if ev_type == ROLL:
            if self.point:
                self.rolls_since_point += 1
                if self.rolls_since_point == 3:
                    # Regress: clear place_6 and place_8 with provenance
                    actions.extend([
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
                    ])
            # Append rule actions for this roll
            actions.extend(self._apply_rules_for_event(event))
            # Journal and return
            self._journal_actions(event, actions)
            return actions

        if ev_type == SEVEN_OUT:
            # Reset state then run rules (some may want to react to seven_out)
            self.point = None
            self.rolls_since_point = 0
            self.on_comeout = True
            actions.extend(self._apply_rules_for_event(event))
            # Journal and return
            self._journal_actions(event, actions)
            return actions

        # Unknown or ancillary event type: still allow rules to look at it
        actions.extend(self._apply_rules_for_event(event))
        self._journal_actions(event, actions)
        return actions

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
        ev = (event.get("event") or event.get("type") or "").lower()
        if ev == SEVEN_OUT:
            self.point = None
            self.rolls_since_point = 0
            self.on_comeout = True
        return None