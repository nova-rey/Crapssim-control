# crapssim_control/controller.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

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
      • rules engine called on every event; actions are merged deterministically (P4C3)
      • per-event CSV journaling (when enabled via spec.run.csv)
      • required adapter shims: update_bets(table) and after_roll(table, event)

    P4C2 upgrades:
      • Canonicalize all inbound events via events.canonicalize_event(...)
      • Stable event fields for rules ('type', 'roll', 'point', 'on_comeout', ...)
      • Snapshot/journaling now includes canonical event fields where useful

    P4C3 upgrades:
      • Deterministic in-event ordering: template → regression → rules
      • Conflict merge within an event; last-wins per bet; clear overrides others
      • Journal only the post-merge final list; annotate with per-event monotonic seq

    P4C4 upgrades:
      • switch_mode side-effect applies IMMEDIATELY within the same event
        (so a switch on point_established affects that event’s template diff).
      • Final action order within an event:
          [all switch_mode actions] → [template/regression] → [other rule actions] → [other/unknown]
        with last-wins conflict resolution among bet actions as before.
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
            self._journal = j
            self._journal_enabled = True
            return j
        except Exception:
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
        return apply_rules(rules, st, event or {})

    # ----- P4C3/P4C4: event-local action merge & (P4C4) pre-merge switch handling -----

    @staticmethod
    def _source_bucket(action: Dict[str, Any]) -> int:
        """
        Precedence buckets: 0=template (including regress), 1=rule, 2=other/unknown.
        Lower bucket index means earlier in ordering. Ordering within a bucket is stable.
        """
        src = (action.get("source") or "").lower()
        if src == "template":
            return 0
        if src == "rule":
            return 1
        return 2

    @staticmethod
    def _is_switch_mode(action: Dict[str, Any]) -> bool:
        return (action.get("action") or "").lower() == "switch_mode"

    @staticmethod
    def _bet_key(action: Dict[str, Any]) -> Optional[str]:
        bt = action.get("bet_type")
        return str(bt) if isinstance(bt, str) and bt else None

    @staticmethod
    def _action_family(action: Dict[str, Any]) -> str:
        """
        Collapse action names into families that should conflict:
          - set/press/reduce considered 'bet_mutate'
          - clear considered 'bet_clear'
          - switch_mode considered 'mode'
          - others fall into their own name
        """
        a = (action.get("action") or "").lower()
        if a in ("set", "press", "reduce"):
            return "bet_mutate"
        if a == "clear":
            return "bet_clear"
        if a == "switch_mode":
            return "mode"
        return a

    def _merge_actions_for_event(self, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deterministic event-local merge:
          • Ordering (by buckets): template → rules → other
          • Within a bucket: keep original order (stable sort)
          • Conflicts among bet actions:
              - Last wins for same bet across the entire event
              - 'clear' overrides any earlier set/press/reduce on same bet
        """
        if not actions:
            return []

        # Stable sort by (bucket, original index)
        sorted_with_index: List[Tuple[int, int, Dict[str, Any]]] = [
            (self._source_bucket(a), idx, a) for idx, a in enumerate(actions)
        ]
        sorted_with_index.sort(key=lambda t: (t[0], t[1]))
        ordered = [a for _, _, a in sorted_with_index]

        # Merge conflicts by tracking the last effective action per bet
        final: List[Dict[str, Any]] = []
        last_for_bet: Dict[str, int] = {}  # bet_type -> index in final

        for a in ordered:
            fam = self._action_family(a)
            if fam in ("bet_mutate", "bet_clear"):
                bk = self._bet_key(a)
                if not bk:
                    final.append(a)
                    continue
                if bk in last_for_bet:
                    prev_idx = last_for_bet[bk]
                    # last wins semantics (clear overrides implicitly by replacement)
                    final[prev_idx] = a
                    last_for_bet[bk] = prev_idx
                else:
                    last_for_bet[bk] = len(final)
                    final.append(a)
            else:
                final.append(a)

        return final

    def _annotate_seq(self, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for i, a in enumerate(actions, start=1):
            if "seq" not in a:
                a["seq"] = i
        return actions

    # ----- P4C4 helpers: split/apply switches BEFORE planning/journaling ----------

    @staticmethod
    def _split_switch_and_other(actions: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Partition actions into (switch_mode actions, others) preserving order."""
        switches: List[Dict[str, Any]] = []
        others: List[Dict[str, Any]] = []
        for a in actions:
            if (a.get("action") or "").lower() == "switch_mode":
                switches.append(a)
            else:
                others.append(a)
        return switches, others

    def _apply_switches_now(self, switch_actions: List[Dict[str, Any]]) -> None:
        """
        Apply mode switches immediately (last one wins). Targets are taken from 'notes' or 'mode'.
        """
        last_target: Optional[str] = None
        for a in switch_actions:
            target = (a.get("notes") or a.get("mode") or "").strip()
            if target:
                last_target = target
        if last_target:
            self.mode = last_target  # takes effect immediately in this event

    # ----- public API used by tests -----

    def handle_event(self, event: Dict[str, Any], current_bets: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Produce a list of Action Envelopes for the given event by:
          1) canonicalizing and updating internal state,
          2) collecting rule-driven actions,
          3) applying any switch_mode immediately (affects same-event planning),
          4) generating template diff/regression actions (using current mode),
          5) merging (deterministic) & annotating seq,
          6) journaling the final envelopes if enabled.
        """
        # Normalize inbound event to the canonical contract
        event = canonicalize_event(event or {})
        ev_type = event.get("type")

        # Aggregate actions pieces per event
        template_and_regress: List[Dict[str, Any]] = []
        rule_actions: List[Dict[str, Any]] = []

        # ----- state updates driven by the canonical event -----
        if ev_type == COMEOUT:
            self.point = None
            self.rolls_since_point = 0
            self.on_comeout = True

            # Rules first → apply switches immediately
            rule_actions = self._apply_rules_for_event(event)
            switches, rule_non_switch = self._split_switch_and_other(rule_actions)
            self._apply_switches_now(switches)

            # No template plan on pure comeout
            final = self._merge_actions_for_event(switches + template_and_regress + rule_non_switch)
            final = self._annotate_seq(final)
            self._journal_actions(event, final)
            return final

        if ev_type == POINT_ESTABLISHED:
            try:
                self.point = int(event.get("point"))
            except Exception:
                self.point = None
            self.rolls_since_point = 0
            self.on_comeout = self.point in (None, 0)

            # Rules first → apply switches so template uses the updated mode
            rule_actions = self._apply_rules_for_event(event)
            switches, rule_non_switch = self._split_switch_and_other(rule_actions)
            self._apply_switches_now(switches)

            # Now render template with (possibly) new mode
            template_and_regress.extend(self._apply_mode_template_plan(current_bets, self.mode))

            final = self._merge_actions_for_event(switches + template_and_regress + rule_non_switch)
            final = self._annotate_seq(final)
            self._journal_actions(event, final)
            return final

        if ev_type == ROLL:
            # Regression logic (template-origin)
            if self.point:
                self.rolls_since_point += 1
                if self.rolls_since_point == 3:
                    template_and_regress.extend([
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

            # Rules → apply switches immediately (even though roll has no template plan)
            rule_actions = self._apply_rules_for_event(event)
            switches, rule_non_switch = self._split_switch_and_other(rule_actions)
            self._apply_switches_now(switches)

            final = self._merge_actions_for_event(switches + template_and_regress + rule_non_switch)
            final = self._annotate_seq(final)
            self._journal_actions(event, final)
            return final

        if ev_type == SEVEN_OUT:
            # Reset state then run rules
            self.point = None
            self.rolls_since_point = 0
            self.on_comeout = True

            rule_actions = self._apply_rules_for_event(event)
            switches, rule_non_switch = self._split_switch_and_other(rule_actions)
            self._apply_switches_now(switches)

            final = self._merge_actions_for_event(switches + rule_non_switch)
            final = self._annotate_seq(final)
            self._journal_actions(event, final)
            return final

        # Unknown or ancillary event type: still allow rules to look at it
        rule_actions = self._apply_rules_for_event(event)
        switches, rule_non_switch = self._split_switch_and_other(rule_actions)
        self._apply_switches_now(switches)

        final = self._merge_actions_for_event(switches + rule_non_switch)
        final = self._annotate_seq(final)
        self._journal_actions(event, final)
        return final

    def state_snapshot(self) -> Dict[str, Any]:
        return {
            "point": self.point,
            "rolls_since_point": self.rolls_since_point,
            "on_comeout": self.on_comeout,
            "mode": getattr(self, "mode", None),
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