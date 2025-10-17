# crapssim_control/controller.py
from __future__ import annotations
 
from typing import Any, Dict, List, Optional, Tuple
import json
from pathlib import Path
import shutil
import zipfile
from datetime import datetime
import hashlib  # P5C5: for content fingerprints

from .templates_rt import render_template as render_runtime_template, diff_bets
from .actions import make_action  # Action Envelope helper
from .rules_rt import apply_rules  # Runtime rules engine
from .csv_journal import CSVJournal  # Per-event journaling
from .events import canonicalize_event, COMEOUT, POINT_ESTABLISHED, ROLL, SEVEN_OUT
from .eval import evaluate, EvalError
from .config import (
    DEMO_FALLBACKS_DEFAULT,
    EMBED_ANALYTICS_DEFAULT,
    STRICT_DEFAULT,
    coerce_flag,
    normalize_demo_fallbacks,
)
from .spec_validation import VALIDATION_ENGINE_VERSION


class ControlStrategy:
    """
    Minimal, test-oriented controller.

    P0·C1 NOTE:
      We introduce inert runtime flags (read from spec only; no behavior change):
        - run.demo_fallbacks (bool, default False)
        - run.strict (bool, default False)
        - run.csv.embed_analytics (bool, default True)
      They are stored in self._flags for later phases but NOT consumed yet.
    """

    _DEMO_NOTICE_PRINTED: bool = False

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

        # -------- P0·C1: Inert flag framework (spec-only, no behavior change) --------
        run_blk = spec.get("run") if isinstance(spec, dict) else {}
        csv_blk = (run_blk or {}).get("csv") if isinstance(run_blk, dict) else {}

        demo_flag = normalize_demo_fallbacks(run_blk if isinstance(run_blk, dict) else None)

        strict_raw = None
        if isinstance(run_blk, dict):
            strict_raw = run_blk.get("strict")
        strict_norm, strict_ok = coerce_flag(strict_raw, default=STRICT_DEFAULT)
        strict_flag = bool(strict_norm) if strict_ok and strict_norm is not None else STRICT_DEFAULT

        embed_raw = None
        if isinstance(csv_blk, dict):
            embed_raw = csv_blk.get("embed_analytics")
        embed_norm, embed_ok = coerce_flag(embed_raw, default=EMBED_ANALYTICS_DEFAULT)
        embed_flag = bool(embed_norm) if embed_ok and embed_norm is not None else EMBED_ANALYTICS_DEFAULT

        # Defaults: demo_fallbacks=False, strict=False, embed_analytics=True
        self._flags: Dict[str, bool] = {
            "demo_fallbacks": demo_flag,
            "strict": strict_flag,
            "embed_analytics": embed_flag,
        }

        if not ControlStrategy._DEMO_NOTICE_PRINTED:
            ControlStrategy._DEMO_NOTICE_PRINTED = True
            status = "ON" if self._flags["demo_fallbacks"] else "OFF"
            print(
                f"[P1·C1] run.demo_fallbacks default={DEMO_FALLBACKS_DEFAULT} → current {status}. "
                "Set run.demo_fallbacks=true (spec or CLI) to enable legacy demo fallbacks."
            )
        # ------------------------------------------------------------------------------

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
            "by_event_type": {},
        }

    # ----- helpers -----

    def _default_mode(self) -> str:
        modes = self.spec.get("modes", {}) or {}
        if "Main" in modes:
            return "Main"
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
        snap = {
            "event_type": event.get("type"),
            "point": self.point,
            "rolls_since_point": self.rolls_since_point,
            "on_comeout": self.on_comeout,
            "mode": getattr(self, "mode", None),
            "units": self._units_from_spec_or_state(),
            "bankroll": self._bankroll_best_effort(),
            "roll": event.get("roll"),
            "event_point": event.get("point"),
            "extra": {
                "mode_change": self._mode_changed_this_event,
                "memory": dict(self.memory) if self.memory else {},
                # P0·C1: include flags in snapshot only if helpful for debugging later (optional)
                # Commented out to keep byte-identical outputs in Phase 0.
                # "flags": dict(self._flags),
            },
        }
        return snap

    def _journal_actions(self, event: Dict[str, Any], actions: List[Dict[str, Any]]) -> None:
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
        mode = mode_name or self.mode or self._default_mode()
        tmpl = (self.spec.get("modes", {}).get(mode) or {}).get("template") or {}
        st = self._current_state_for_eval()
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
        rules = self.spec.get("rules") if isinstance(self.spec, dict) else None
        st = self._current_state_for_eval()
        return apply_rules(rules, st, event or {})

    # ----- P4C3/P4C4 merge helpers -----

    @staticmethod
    def _source_bucket(action: Dict[str, Any]) -> int:
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
        if not actions:
            return []
        sorted_with_index: List[Tuple[int, int, Dict[str, Any]]] = [
            (self._source_bucket(a), idx, a) for idx, a in enumerate(actions)
        ]
        sorted_with_index.sort(key=lambda t: (t[0], t[1]))
        ordered = [a for _, _, a in sorted_with_index]

        final: List[Dict[str, Any]] = []
        last_for_bet: Dict[str, int] = {}

        for a in ordered:
            fam = self._action_family(a)
            if fam in ("bet_mutate", "bet_clear"):
                bk = self._bet_key(a)
                if not bk:
                    final.append(a)
                    continue
                if bk in last_for_bet:
                    prev_idx = last_for_bet[bk]
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

    @staticmethod
    def _split_switch_setvar_other(actions: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
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
        last_target: Optional[str] = None
        for a in switch_actions:
            target = (a.get("notes") or a.get("mode") or "").strip()
            if target:
                last_target = target
        if not last_target:
            return False
        prev = self.mode
        self.mode = last_target
        return self.mode != prev

    def _apply_setvars_now(self, setvar_actions: List[Dict[str, Any]], event: Dict[str, Any]) -> None:
        if not setvar_actions:
            return
        for a in setvar_actions:
            var = a.get("var") or a.get("name")
            if not isinstance(var, str) or not var.strip():
                continue
            var = var.strip()

            if "value" in a:
                val_expr = a.get("value")
            elif "amount" in a:
                val_expr = a.get("amount")
            else:
                val_expr = a.get("notes")

            st = self._current_state_for_eval()
            try:
                if isinstance(val_expr, (int, float, bool)):
                    new_val = val_expr
                else:
                    new_val = evaluate(str(val_expr), state=st, event=event)
                self.memory[var] = new_val
            except (EvalError, Exception):
                continue

    # ----- public API used by tests -----

    def handle_event(self, event: Dict[str, Any], current_bets: Dict[str, Any]) -> List[Dict[str, Any]]:
        # Reset per-event flags
        self._mode_changed_this_event = False

        # Normalize inbound event
        event = canonicalize_event(event or {})
        ev_type = event.get("type")

        template_and_regress: List[Dict[str, Any]] = []
        rule_actions: List[Dict[str, Any]] = []

        if ev_type == COMEOUT:
            self.point = None
            self.rolls_since_point = 0
            self.on_comeout = True

            rule_actions = self._apply_rules_for_event(event)
            switches, setvars, rule_non_special = self._split_switch_setvar_other(rule_actions)
            if switches:
                self._mode_changed_this_event = self._apply_switches_now(switches) or self._mode_changed_this_event
            if setvars:
                self._apply_setvars_now(setvars, event)

            final = self._merge_actions_for_event(switches + template_and_regress + rule_non_special)
            final = self._annotate_seq(final)
            self._journal_actions(event, final)
            self._bump_stats(ev_type, final)
            return final

        if ev_type == POINT_ESTABLISHED:
            try:
                self.point = int(event.get("point"))
            except Exception:
                self.point = None
            self.rolls_since_point = 0
            self.on_comeout = self.point in (None, 0)

            rule_actions = self._apply_rules_for_event(event)
            switches, setvars, rule_non_special = self._split_switch_setvar_other(rule_actions)
            if switches:
                self._mode_changed_this_event = self._apply_switches_now(switches) or self._mode_changed_this_event
            if setvars:
                self._apply_setvars_now(setvars, event)

            template_and_regress.extend(self._apply_mode_template_plan(current_bets, self.mode))

            # Fallback: if template produced no actions on a 6 point, synthesize one.
            if (
                self._flags.get("demo_fallbacks", False)
                and not template_and_regress
                and self.point == 6
            ):
                amt = self._units_from_spec_or_state() or 12.0
                template_and_regress.append(
                    make_action(
                        "set",
                        bet_type="place_6",
                        amount=amt,
                        # mark as 'rule' so bucket ordering keeps switch first
                        source="rule",
                        id_="template:fallback_place6",
                        notes="fallback action for POINT_ESTABLISHED(6)",
                    )
                )

            final = self._merge_actions_for_event(switches + template_and_regress + rule_non_special)
            final = self._annotate_seq(final)
            self._journal_actions(event, final)
            self._bump_stats(ev_type, final)
            return final

        if ev_type == ROLL:
            if self.point:
                self.rolls_since_point += 1
                if self._flags.get("demo_fallbacks", False) and self.rolls_since_point == 3:
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

            rule_actions = self._apply_rules_for_event(event)
            switches, setvars, rule_non_special = self._split_switch_setvar_other(rule_actions)
            if switches:
                self._mode_changed_this_event = self._apply_switches_now(switches) or self._mode_changed_this_event
            if setvars:
                self._apply_setvars_now(setvars, event)

            final = self._merge_actions_for_event(switches + template_and_regress + rule_non_special)
            final = self._annotate_seq(final)
            self._journal_actions(event, final)
            self._bump_stats(ev_type, final)
            return final

        if ev_type == SEVEN_OUT:
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
            self._bump_stats(ev_type, final)
            return final

    def _bump_stats(self, ev_type: Optional[str], actions: List[Dict[str, Any]]) -> None:
        ev = (ev_type or "").lower()
        self._stats["events_total"] += 1
        self._stats["actions_total"] += len(actions)
        map_ = self._stats["by_event_type"]
        map_[ev] = int(map_.get(ev, 0)) + 1

    # ---------------------- P5C2/P5C3: finalize, meta, report ----------------------

    def _read_meta_path_from_spec(self) -> Optional[Path]:
        """
        Return the configured meta.json destination, being lenient about where
        specs may place it:
          • run.memory.meta_path        (primary)
          • run.meta_path               (alt)
          • run.meta.path               (alt block)
        """
        run_blk = self.spec.get("run") if isinstance(self.spec, dict) else {}
        meta_path: Optional[str] = None

        if isinstance(run_blk, dict):
            # Primary: run.memory.meta_path
            mem_blk = run_blk.get("memory")
            if isinstance(mem_blk, dict):
                meta_path = mem_blk.get("meta_path") or meta_path

            # Alt: run.meta_path
            if not meta_path:
                meta_path = run_blk.get("meta_path") or meta_path

            # Alt block: run.meta.path
            if not meta_path:
                meta_blk = run_blk.get("meta")
                if isinstance(meta_blk, dict):
                    meta_path = meta_blk.get("path") or meta_blk.get("meta_path") or meta_path

        return Path(meta_path) if isinstance(meta_path, str) and meta_path.strip() else None

    def _report_cfg_from_spec(self) -> Tuple[Optional[Path], bool]:
        """
        Resolve (report_path, auto_flag) from either run.memory or run.report.
        Accepts keys: path / report_path and auto / auto_report
        """
        run_blk = self.spec.get("run") if isinstance(self.spec, dict) else {}
        mem_blk = (run_blk or {}).get("memory") if isinstance(run_blk, dict) else {}
        rep_blk = (run_blk or {}).get("report") if isinstance(run_blk, dict) else {}

        path_val = None
        auto_val = None

        if isinstance(mem_blk, dict):
            path_val = mem_blk.get("report_path", path_val)
            auto_val = mem_blk.get("auto_report", auto_val)
            if auto_val is None:
                auto_val = mem_blk.get("auto", auto_val)

        if isinstance(rep_blk, dict):
            path_val = rep_blk.get("path", path_val)
            if auto_val is None:
                auto_val = rep_blk.get("auto", auto_val)
            if auto_val is None:
                auto_val = rep_blk.get("auto_report", auto_val)

        report_path = Path(path_val) if isinstance(path_val, str) and path_val.strip() else None
        auto = bool(auto_val) if auto_val is not None else False
        return report_path, auto

    def generate_report(self, report_path: Optional[str | Path] = None) -> Dict[str, Any]:
        """
        Build a run report JSON and return it as a dict.
        Prefers meta.json for identity/memory if present; otherwise falls back to
        in-memory controller state and CSV config. If a path is configured, also writes it.
        """
        # Resolve output path (support both run.report and run.memory.report_path)
        if report_path is None:
            cfg_path, _ = self._report_cfg_from_spec()
            report_path = cfg_path

        # Try meta.json if configured and present
        identity: Dict[str, Any] = {}
        memory: Dict[str, Any] = {}
        meta_path = self._read_meta_path_from_spec()

        if meta_path and meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                identity = dict(meta.get("identity") or {})
                memory = dict(meta.get("memory") or {})
            except Exception:
                pass

        if not identity:
            j = self._ensure_journal()
            identity = {
                "run_id": getattr(j, "run_id", None),
                "seed": getattr(j, "seed", None),
            }
        if not memory:
            memory = dict(self.memory)

        summary = {
            "events_total": int(self._stats.get("events_total", 0)),
            "actions_total": int(self._stats.get("actions_total", 0)),
            "by_event_type": dict(self._stats.get("by_event_type", {})),
        }

        # Include CSV and meta paths under source_files (tests read these)
        j = self._ensure_journal()
        source_files = {
            "csv": str(getattr(j, "path")) if j is not None else None,
            # record configured meta path string even if file doesn't exist
            "meta": str(meta_path) if meta_path is not None else None,
        }

        report: Dict[str, Any] = {
            "identity": identity,
            "summary": summary,
            "memory": memory,
            "mode": getattr(self, "mode", None),
            "point": self.point,
            "on_comeout": self.on_comeout,
            "source_files": source_files,
            "metadata": {
                "demo_fallbacks_default": DEMO_FALLBACKS_DEFAULT,
                "run_flags": {
                    "demo_fallbacks": bool(self._flags.get("demo_fallbacks", False)),
                    "strict": bool(self._flags.get("strict", False)),
                    "embed_analytics": bool(
                        self._flags.get("embed_analytics", EMBED_ANALYTICS_DEFAULT)
                    ),
                },
            },
        }

        report["validation_engine"] = VALIDATION_ENGINE_VERSION

        # Keep the old csv.path hint too (legacy/compat)
        try:
            report["csv"] = {"path": str(getattr(j, "path")) if j is not None else None}
        except Exception:
            report["csv"] = {"path": None}

        # Write to disk if a path is provided/configured
        if isinstance(report_path, (str, Path)) and str(report_path):
            p = Path(report_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            try:
                p.write_text(
                    json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                    encoding="utf-8",
                )
            except Exception:
                pass

        return report

    # ---------------------- P5C5: export bundle ----------------------

    def _export_cfg_from_spec(self) -> Tuple[Optional[Path], bool]:
        """
        Resolve export root and compress flag, lenient across:
          • run.report.export.{path,compress}
          • run.export.{path,compress}
        """
        run_blk = self.spec.get("run") if isinstance(self.spec, dict) else {}
        export_root = None
        compress = False

        if isinstance(run_blk, dict):
            # Prefer nested under report
            rep = run_blk.get("report")
            if isinstance(rep, dict):
                exp = rep.get("export")
                if isinstance(exp, dict):
                    export_root = exp.get("path") or export_root
                    if "compress" in exp:
                        compress = bool(exp.get("compress"))
            # Fall back to run.export
            exp = run_blk.get("export")
            if isinstance(exp, dict):
                export_root = exp.get("path") or export_root
                if "compress" in exp:
                    compress = bool(exp.get("compress"))

        return (Path(export_root) if isinstance(export_root, str) and export_root.strip() else None, bool(compress))

    # ---- P5C5 dedup/versioning helpers (folder mode only) ----

    @staticmethod
    def _fingerprint_file(path: Path, *, chunk_size: int = 1024 * 1024) -> Optional[str]:
        """Return SHA-256 hex digest of file contents, or None if not readable."""
        try:
            h = hashlib.sha256()
            with path.open("rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return None

    @staticmethod
    def _export_copy(src: Path, dst_dir: Path, *, versioning: bool = True) -> Tuple[Path, bool, Optional[str]]:
        """
        Copy src into dst_dir with content-aware behavior.
        Returns (dst_path, copied_bool, fingerprint_hex).
          - If a file of same basename exists and contents are identical → skip copy (copied=False).
          - If different and versioning=False → overwrite existing basename.
          - If different and versioning=True → create 'name-vN.ext' (N increments).
        """
        dst_dir.mkdir(parents=True, exist_ok=True)
        base = src.name
        dst = dst_dir / base

        src_fp = ControlStrategy._fingerprint_file(src)

        if dst.exists():
            dst_fp = ControlStrategy._fingerprint_file(dst)
            if dst_fp and src_fp and dst_fp == src_fp:
                return dst, False, src_fp  # identical, no copy

            if not versioning:
                shutil.copy2(src, dst)
                return dst, True, src_fp

            stem = dst.stem
            suffix = dst.suffix
            n = 1
            while True:
                cand = dst_dir / f"{stem}-v{n}{suffix}"
                if not cand.exists():
                    shutil.copy2(src, cand)
                    return cand, True, src_fp
                # If an older version has identical content, reuse it:
                cand_fp = ControlStrategy._fingerprint_file(cand)
                if cand_fp and src_fp and cand_fp == src_fp:
                    return cand, False, src_fp
                n += 1
        else:
            shutil.copy2(src, dst)
            return dst, True, src_fp

    def export_bundle(self, export_root: Optional[str | Path] = None, compress: Optional[bool] = None) -> Optional[Path]:
        """
        Export run artifacts (csv/meta/report) into a dated folder or a .zip bundle.
        Returns the path to the export folder or zip file, or None on failure/no config.
        """
        cfg_root, cfg_comp = self._export_cfg_from_spec()
        if export_root is None:
            export_root = cfg_root
        if export_root is None:
            return None
        if compress is None:
            compress = cfg_comp

        export_root = Path(export_root)
        export_root.mkdir(parents=True, exist_ok=True)

        # Figure out artifacts
        j = self._ensure_journal()
        csv_path = Path(getattr(j, "path")) if (j is not None and getattr(j, "path", None)) else None
        meta_path = self._read_meta_path_from_spec()
        report_path, _auto = self._report_cfg_from_spec()

        # If report is configured but does not exist yet, try to generate it once.
        if report_path and not report_path.exists():
            try:
                self.generate_report(report_path)
            except Exception:
                pass

        # Build identity
        identity = {
            "run_id": getattr(j, "run_id", None),
            "seed": getattr(j, "seed", None),
        }

        # Destination naming
        stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        base_name = (identity.get("run_id") or "run")
        folder_name = f"{base_name}_{stamp}"

        # Relative names (preferred basenames)
        rel_csv = "journal.csv" if csv_path else None
        rel_meta = "meta.json" if meta_path else None
        rel_report = "report.json" if report_path else None

        if not compress:
            # Folder export (with content-aware copy + versioning)
            dest_dir = export_root / folder_name
            dest_dir.mkdir(parents=True, exist_ok=True)

            artifacts: Dict[str, Optional[str]] = {}
            fingerprints: Dict[str, Optional[str]] = {}

            if csv_path and csv_path.exists():
                dst, _copied, fp = self._export_copy(csv_path, dest_dir, versioning=True)
                artifacts["csv"] = str(dst.relative_to(dest_dir))
                fingerprints["csv"] = fp
            if meta_path and meta_path.exists():
                dst, _copied, fp = self._export_copy(meta_path, dest_dir, versioning=True)
                artifacts["meta"] = str(dst.relative_to(dest_dir))
                fingerprints["meta"] = fp
            else:
                artifacts["meta"] = None
                fingerprints["meta"] = None
            if report_path and report_path.exists():
                dst, _copied, fp = self._export_copy(report_path, dest_dir, versioning=True)
                artifacts["report"] = str(dst.relative_to(dest_dir))
                fingerprints["report"] = fp

            manifest = {
                "identity": identity,
                "artifacts": artifacts,
                "fingerprints": fingerprints,
            }
            (dest_dir / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                encoding="utf-8",
            )
            return dest_dir

        # Zip export (unchanged behavior)
        zip_path = export_root / f"{folder_name}.zip"
        artifacts_zip: Dict[str, Optional[str]] = {}
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if csv_path and csv_path.exists():
                zf.write(csv_path, arcname=rel_csv or "journal.csv")
                artifacts_zip["csv"] = rel_csv or "journal.csv"
            if meta_path and meta_path.exists():
                zf.write(meta_path, arcname=rel_meta or "meta.json")
                artifacts_zip["meta"] = rel_meta or "meta.json"
            else:
                artifacts_zip["meta"] = None
            if report_path and report_path.exists():
                zf.write(report_path, arcname=rel_report or "report.json")
                artifacts_zip["report"] = rel_report or "report.json"

            manifest = {
                "identity": identity,
                "artifacts": artifacts_zip,
            }
            zf.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
            )

        return zip_path

    def finalize_run(self) -> None:
        """
        Emit a one-row summary to CSV (if enabled), optionally write meta.json,
        generate a report if auto-report is enabled, and export a bundle if configured.
        """
        j = self._ensure_journal()  # may be None if CSV disabled

        identity = {
            "run_id": getattr(j, "run_id", None),
            "seed": getattr(j, "seed", None),
        }
        summary_event = {
            "type": "summary",
            "point": self.point,
            "roll": 0,
            "on_comeout": self.on_comeout,
            "extra": {
                "summary": True,
                "identity": identity,
                "stats": dict(self._stats),
                "memory": dict(self.memory) if self.memory else {},
            },
        }

        if j is not None:
            try:
                summary_action = make_action(
                    "switch_mode",
                    bet_type=None,
                    amount=None,
                    source="rule",
                    id_="summary:run",
                    notes="end_of_run",
                )
                j.write_actions([summary_action], snapshot=summary_event)
            except Exception:
                pass

        # Optional meta.json dump if configured
        meta_path = self._read_meta_path_from_spec()
        if meta_path:
            try:
                out = {
                    "identity": identity,
                    "stats": dict(self._stats),
                    "memory": dict(self.memory),
                    "mode": getattr(self, "mode", None),
                    "point": self.point,
                    "on_comeout": self.on_comeout,
                }
                meta_path.parent.mkdir(parents=True, exist_ok=True)
                meta_path.write_text(
                    json.dumps(out, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                    encoding="utf-8",
                )
            except Exception:
                pass

        # P5C3: auto-report if enabled
        report_path, auto = self._report_cfg_from_spec()
        if auto and report_path is not None:
            self.generate_report(report_path)

        # P5C5: auto-export if configured
        exp_root, _comp = self._export_cfg_from_spec()
        if exp_root is not None:
            try:
                self.export_bundle(exp_root)  # use configured compress flag by default
            except Exception:
                # fail-open: exporting is optional
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
        return None

    def after_roll(self, table: Any, event: Dict[str, Any]) -> None:
        ev = (event.get("event") or event.get("type") or "").lower()
        if ev == SEVEN_OUT:
            self.point = None
            self.rolls_since_point = 0
            self.on_comeout = True
        return None