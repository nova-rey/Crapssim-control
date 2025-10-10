# crapssim_control/controller.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .templates_rt import render_template as render_runtime_template, diff_bets
from .actions import make_action  # Action Envelope helper
from .rules_rt import apply_rules  # Runtime rules engine
from .csv_journal import CSVJournal  # Per-event journaling
from .events import canonicalize_event, COMEOUT, POINT_ESTABLISHED, ROLL, SEVEN_OUT
from .eval import evaluate, EvalError


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
      • New 'setvar' rule action to persist custom variables across events.
        Applied before template rendering so templates/rules can use them.
      • Snapshot.extra includes {"mode_change": bool, "memory": {...}} for journaling.

    P5C1 upgrades:
      • In-RAM per-run stats (_stats) counting events/actions (no persistence between runs).
      • finalize_run() writes a one-row summary to CSV (via extra JSON) when journaling is enabled.
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

        # P4C4: persistent user memory (cross-event within a single run)
        self.memory: Dict[str, Any] = {}

        # Journaling: lazy-init on first use
        self._journal: Optional[CSVJournal] = None
        self._journal_enabled: Optional[bool] = None  # tri-state: None unknown, True/False decided

        # P4C4: per-event flag captured in snapshot.extra
        self._mode_changed_this_event: bool = False

        # P5C1: simple in-RAM run stats
        self._stats: Dict[str, Any] = {
            "events_total": 0,
            "actions_total": 0,
            "by_event_type": {},  # e.g., {"comeout": 1, "point_established": 3, ...}
        }

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

        # Include controller memory so rules/templates can use it
        st.update(self.memory)

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
            # P5C1: ensure the CSV file exists with a header immediately
            j.ensure_header()
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
            # Enriched extra payload consumed by CSVJournal
            "extra": {
                "mode_change": self._mode_changed_this_event,
                "memory": dict(self.memory) if self.memory else {},
            },
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

    # ----- P4C3/P4C4: event-local action merge & pre-merge switch/setvar handling -----

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
    def _is_setvar(action: Dict[str, Any]) -> bool:
        return (action.get("action") or "").lower() == "setvar"

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
          - setvar considered 'setvar'
          - others fall into their own name
        """
        a = (action.get("action") or "").lower()
        if a in ("set", "press", "reduce"):
            return "bet_mutate"
        if a == "clear":
            return "bet_clear"
        if a == "switch_mode":
            return "mode"
        if a == "setvar":
            return "setvar"
        return a

    def _merge_actions_for_event(self, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deterministic event-local merge:
          • Ordering (by buckets): template → rules → other
          • Within a bucket: keep original order (stable sort)
          • Conflicts among bet actions:
              - Last wins for same bet across the entire event
              - 'clear' overrides any earlier set/press/reduce on same bet
          • setvar/mode actions are independent (no bet conflict resolution)
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
                    final[prev_idx] = a  # last wins; clear overrides by replacement
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

    # ----- P4C4 helpers: split/apply switches & setvars BEFORE planning/journaling ----------

    @staticmethod
    def _split_switch_setvar_other(actions: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Partition actions into (switch_mode actions, setvar actions, others) preserving order."""
        switches: List[Dict[str, Any]] = []
        setvars: List[Dict[str, Any]] = []
        others: List[Dict[str, Any]] = []
        for a in actions:
            act = (a.get("action") or "").lower()
            if act == "switch_mode":
                switches.append(a)
            elif act == "setvar":
                setvars.append(a)
            else:
                others.append(a)
        return switches, setvars, others

    def _apply_switches_now(self, switch_actions: List[Dict[str, Any]]) -> bool:
        """
        Apply mode switches immediately (last one wins). Targets are taken from 'notes' or 'mode'.
        Returns True if mode changed this call.
        """
        last_target: Optional[str] = None
        for a in switch_actions:
            target = (a.get("notes") or a.get("mode") or "").strip()
            if target:
                last_target = target
        if not last_target:
            return False
        prev = self.mode
        self.mode = last_target  # takes effect immediately in this event
        return self.mode != prev

    def _apply_setvars_now(self, setvar_actions: List[Dict[str, Any]], event: Dict[str, Any]) -> None:
        """
        Apply 'setvar' actions immediately so templates/rules can see updated memory.
        Accepts either:
          • explicit keys: {'action':'setvar','var':'win_streak','value':'win_streak+1'}
          • or a fallback string in 'notes' as the value expression with 'var' provided.
        Non-fatal on errors; silently skips bad entries.
        """
        if not setvar_actions:
            return
        for a in setvar_actions:
            # name of the variable
            var = a.get("var") or a.get("name")
            if not isinstance(var, str) or not var.strip():
                continue
            var = var.strip()

            # expression/value
            if "value" in a:
                val_expr = a.get("value")
            elif "amount" in a:
                # allow amount as a numeric shortcut
                val_expr = a.get("amount")
            else:
                val_expr = a.get("notes")  # last-ditch textual expr

            st = self._current_state_for_eval()
            try:
                # If value is already numeric/bool, keep as-is; else evaluate as expression string
                if isinstance(val_expr, (int, float, bool)):
                    new_val = val_expr
                else:
                    new_val = evaluate(str(val_expr), state=st, event=event)
                self.memory[var] = new_val
            except (EvalError, Exception):
                # ignore bad expressions; fail-open
                continue

    # ----- public API used by tests -----

    def handle_event(self, event: Dict[str, Any], current_bets: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Produce a list of Action Envelopes for the given event by:
          1) canonicalizing and updating internal state,
          2) collecting rule-driven actions,
          3) applying any switch_mode immediately (affects same-event planning),
          4) applying any setvar immediately (memory available to template),
          5) generating template diff/regression actions (using current mode),
          6) merging (deterministic) & annotating seq,
          7) journaling the final envelopes if enabled.
        """
        # Reset per-event flags
        self._mode_changed_this_event = False

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

            # Rules first → apply switches & setvars immediately
            rule_actions = self._apply_rules_for_event(event)
            switches, setvars, rule_non_special = self._split_switch_setvar_other(rule_actions)
            if switches:
                self._mode_changed_this_event = self._apply_switches_now(switches) or self._mode_changed_this_event
            if setvars:
                self._apply_setvars_now(setvars, event)

            # No template plan on pure comeout
            final = self._merge_actions_for_event(switches + template_and_regress + rule_non_special)
            final = self._annotate_seq(final)
            self._journal_actions(event, final)

            # P5C1: update stats
            self._bump_stats(ev_type, final)
            return final

        if ev_type == POINT_ESTABLISHED:
            try:
                self.point = int(event.get("point"))
            except Exception:
                self.point = None
            self.rolls_since_point = 0
            self.on_comeout = self.point in (None, 0)

            # Rules first → apply switches and setvars so template uses updated mode/memory
            rule_actions = self._apply_rules_for_event(event)
            switches, setvars, rule_non_special = self._split_switch_setvar_other(rule_actions)
            if switches:
                self._mode_changed_this_event = self._apply_switches_now(switches) or self._mode_changed_this_event
            if setvars:
                self._apply_setvars_now(setvars, event)

            # Now render template with (possibly) new mode and memory
            template_and_regress.extend(self._apply_mode_template_plan(current_bets, self.mode))

            final = self._merge_actions_for_event(switches + template_and_regress + rule_non_special)
            final = self._annotate_seq(final)
            self._journal_actions(event, final)

            # P5C1: update stats
            self._bump_stats(ev_type, final)
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

            # Rules → apply switches & setvars immediately
            rule_actions = self._apply_rules_for_event(event)
            switches, setvars, rule_non_special = self._split_switch_setvar_other(rule_actions)
            if switches:
                self._mode_changed_this_event = self._apply_switches_now(switches) or self._mode_changed_this_event
            if setvars:
                self._apply_setvars_now(setvars, event)

            final = self._merge_actions_for_event(switches + template_and_regress + rule_non_special)
            final = self._annotate_seq(final)
            self._journal_actions(event, final)

            # P5C1: update stats
            self._bump_stats(ev_type, final)
            return final

        if ev_type == SEVEN_OUT:
            # Reset state then run rules
            self.point = None
            self.rolls_since_point = 0
            self.on_comeout = True

            rule_actions = self._apply_rules_for_event(event)
            switches, setvars, rule_non_special = self._split_switch_setvar_other(rule_actions)
            if switches:
                self._mode_changed_this_event = self._apply_switches_now(switches) or self._mode_changed_this_event
            if setvars:
                self._apply_setvars_now(setvars, event)

            final = self._merge_actions_for_event(switches + rule_non_special)
            final = self._annotate_seq(final)
            self._journal_actions(event, final)

            # P5C1: update stats
            self._bump_stats(ev_type, final)
            return final

        # Unknown or ancillary event type: still allow rules to look at it
        rule_actions = self._apply_rules_for_event(event)
        switches, setvars, rule_non_special = self._split_switch_setvar_other(rule_actions)
        if switches:
            self._mode_changed_this_event = self._apply_switches_now(switches) or self._mode_changed_this_event
        if setvars:
            self._apply_setvars_now(setvars, event)

        final = self._merge_actions_for_event(switches + rule_non_special)
        final = self._annotate_seq(final)
        self._journal_actions(event, final)

        # P5C1: update stats
        self._bump_stats(ev_type, final)
        return final

    def _bump_stats(self, ev_type: Optional[str], actions: List[Dict[str, Any]]) -> None:
        ev = (ev_type or "").lower()
        self._stats["events_total"] += 1
        self._stats["actions_total"] += len(actions)
        map_ = self._stats["by_event_type"]
        map_[ev] = int(map_.get(ev, 0)) + 1

    def finalize_run(self) -> None:
        """
        Optional call at the end of a run to emit a single summary row to CSV (if enabled).
        No-op if journaling is disabled.
        The summary content lives in the 'extra' JSON (merged by CSVJournal).
        """
        j = self._ensure_journal()
        if j is None:
            return

        # Build a synthetic 'summary' snapshot. event_type isn't validated by the CSV writer.
        summary_event = {
            "type": "summary",
            "point": self.point,
            "roll": 0,
            "on_comeout": self.on_comeout,
            # Merge-able extra block; CSVJournal will include this as JSON in 'extra'
            "extra": {
                "summary": True,
                "stats": dict(self._stats),
                "memory": dict(self.memory) if self.memory else {},
            },
        }

        # Emit a single benign envelope. We use switch_mode to avoid requiring bet_type/amount.
        summary_action = make_action(
            "switch_mode",
            bet_type=None,
            amount=None,
            source="rule",
            id_="summary:run",
            notes="end_of_run",
        )

        try:
            j.write_actions([summary_action], snapshot=summary_event)  # one row summary
        except Exception:
            # Fail-open; summary is optional
            pass

    def state_snapshot(self) -> Dict[str, Any]:
        return {
            "point": self.point,
            "rolls_since_point": self.rolls_since_point,
            "on_comeout": self.on_comeout,
            "mode": getattr(self, "mode", None),
            "memory": dict(self.memory),
            "stats": dict(self._stats),
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