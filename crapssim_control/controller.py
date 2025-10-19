# crapssim_control/controller.py
from __future__ import annotations
 
from dataclasses import asdict, is_dataclass
from typing import Any, Deque, Dict, List, Optional, Tuple
import json
import logging
from pathlib import Path
import platform
import shutil
import zipfile
from datetime import datetime
from uuid import uuid4
from types import SimpleNamespace
import hashlib  # P5C5: for content fingerprints
import time
from collections import deque
import subprocess

from .templates import render_template as render_runtime_template, diff_bets
from .actions import make_action  # Action Envelope helper
from .rules_engine import apply_rules  # Runtime rules engine
from .rules_engine.evaluator import evaluate_rules
from crapssim_control.rules_engine.actions import ACTIONS, is_legal_timing
from .rules_engine.journal import DecisionJournal, JournalWriter
from .rules_engine.schema import validate_ruleset
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
from .analytics.tracker import Tracker
from .analytics.types import HandCtx, RollCtx, SessionCtx
from .manifest import generate_manifest

logger = logging.getLogger("CSC.Controller")
from .schemas import JOURNAL_SCHEMA_VERSION, SUMMARY_SCHEMA_VERSION
from .integrations.hooks import Outbound
from .integrations.evo_hooks import EvoBridge
from crapssim_control.integrations.webhooks import WebhookPublisher
from crapssim_control.external.command_channel import CommandQueue
from crapssim_control.external.command_tape import CommandTape
from crapssim_control.external.http_api import HTTPServerHandle, start_http_server


class _ConfigAccessor:
    def __init__(self, data: dict | None):
        if isinstance(data, dict):
            self._data = data
        else:
            self._data = {}

    def get(self, key: str | None, default=None):
        if not key:
            return self._data
        current = self._data
        for part in str(key).split('.'):
            if isinstance(current, dict):
                if part in current:
                    current = current[part]
                else:
                    return default
            else:
                return default
            if current is None:
                return default
        if isinstance(current, dict):
            try:
                return SimpleNamespace(**current)
            except TypeError:
                return current
        return current



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
        spec_deprecations: Optional[List[Dict[str, Any]]] = None,
        *,
        spec_path: Optional[str | Path] = None,
        cli_flags: Optional[Any] = None,
    ) -> None:
        embedded_deprecations: List[Dict[str, Any]] = []
        if spec_deprecations is not None:
            embedded_deprecations = list(spec_deprecations)
        else:
            raw = spec.pop("_csc_spec_deprecations", []) if isinstance(spec, dict) else []
            if isinstance(raw, list):
                embedded_deprecations = [
                    record
                    for record in raw
                    if isinstance(record, dict)
                ]
        self._spec_deprecations: List[Dict[str, Any]] = embedded_deprecations

        self.spec = spec
        self.config = _ConfigAccessor(spec if isinstance(spec, dict) else {})
        self._spec_path: Optional[str] = str(spec_path) if spec_path is not None else None
        self._cli_flags_context: Dict[str, Any] = self._normalize_cli_flags(cli_flags)
        self.engine_version: str = getattr(self, "engine_version", "CrapsSim-Control")
        if self.engine_version == "unknown":
            self.engine_version = "CrapsSim-Control"
        self._engine_build_hash: str = self._detect_build_hash()
        self._run_id: str = str(uuid4())
        self._seed_value: Optional[int] = None
        self._export_paths: Dict[str, Optional[str]] = {}
        self._command_tape: Optional[CommandTape] = None
        self._command_tape_path: Optional[str] = None
        self._replay_commands: Deque[Dict[str, Any]] = deque()
        self.external_mode, self._external_mode_source = self._resolve_external_mode()
        self._command_tape_path = self._resolve_command_tape_path()
        if self.external_mode == "replay":
            self._load_replay_tape()
        elif self._command_tape_path:
            self._command_tape = CommandTape(self._command_tape_path)
        self._outbound: Outbound = Outbound()
        self._webhook_url_source: str = "default"
        self._webhook_url_actual: Optional[str] = None
        self._webhook_url_present: bool = False
        self._webhook_timeout: float = 2.0
        self._outbound_run_started: bool = False
        self._outbound_run_finished: bool = False
        webhook_cfg = self.config.get("run.webhooks", None)
        default_targets = ["http://127.0.0.1:1880/webhook"]
        targets_value = getattr(webhook_cfg, "targets", None)
        if isinstance(targets_value, str):
            targets = [targets_value]
        elif isinstance(targets_value, (list, tuple, set)):
            targets = [str(t) for t in targets_value]
        elif targets_value is None:
            targets = list(default_targets)
        else:
            targets = list(default_targets)
        try:
            timeout_value = getattr(webhook_cfg, "timeout", 2.0)
        except AttributeError:
            timeout_value = 2.0
        try:
            webhook_timeout = float(timeout_value)
        except (TypeError, ValueError):
            webhook_timeout = 2.0
        enabled_raw = self.config.get("run.webhooks.enabled", True)
        if isinstance(enabled_raw, bool):
            webhook_enabled = enabled_raw
        else:
            enabled_norm, enabled_ok = coerce_flag(enabled_raw, default=True)
            if enabled_ok and enabled_norm is not None:
                webhook_enabled = bool(enabled_norm)
            elif enabled_ok and enabled_norm is None:
                webhook_enabled = True
            else:
                webhook_enabled = bool(enabled_raw)
        self.webhooks = WebhookPublisher(targets=targets, enabled=webhook_enabled, timeout=webhook_timeout)
        if self.external_mode == "replay":
            self.webhooks.enabled = False
        self.table_cfg = table_cfg or spec.get("table") or {}
        self.point: Optional[int] = None
        self.rolls_since_point: int = 0
        self.on_comeout: bool = True

        # -------- P0·C1: Inert flag framework (spec-only, no behavior change) --------
        run_blk = spec.get("run") if isinstance(spec, dict) else {}
        cli_sources_raw: Dict[str, str] = {}
        if isinstance(run_blk, dict):
            raw_sources = run_blk.get("_csc_flag_sources")
            if isinstance(raw_sources, dict):
                cli_sources_raw = {str(k): str(v) for k, v in raw_sources.items()}
            run_blk.pop("_csc_flag_sources", None)
        csv_blk = (run_blk or {}).get("csv") if isinstance(run_blk, dict) else {}

        self._apply_run_identity_from_spec(run_blk, csv_blk)

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

        # Track provenance for run flags (default/spec/cli)
        run_dict = run_blk if isinstance(run_blk, dict) else {}
        csv_dict = csv_blk if isinstance(csv_blk, dict) else {}

        flag_sources: Dict[str, str] = {}

        if cli_sources_raw.get("demo_fallbacks") == "cli":
            flag_sources["demo_fallbacks"] = "cli"
        elif isinstance(run_dict, dict) and "demo_fallbacks" in run_dict:
            flag_sources["demo_fallbacks"] = "spec"
        else:
            flag_sources["demo_fallbacks"] = "default"

        if cli_sources_raw.get("strict") == "cli":
            flag_sources["strict"] = "cli"
        elif isinstance(run_dict, dict) and "strict" in run_dict:
            flag_sources["strict"] = "spec"
        else:
            flag_sources["strict"] = "default"

        if cli_sources_raw.get("embed_analytics") == "cli":
            flag_sources["embed_analytics"] = "cli"
        elif isinstance(csv_dict, dict) and "embed_analytics" in csv_dict:
            flag_sources["embed_analytics"] = "spec"
        else:
            flag_sources["embed_analytics"] = "default"

        cli_flag_sources = self._cli_flags_context
        if isinstance(cli_flag_sources, dict):
            for key in ("demo_fallbacks", "strict", "embed_analytics"):
                src_key = f"{key}_source"
                if cli_flag_sources.get(src_key) == "cli":
                    flag_sources[key] = "cli"

        self._flag_sources = flag_sources

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

        # P5C3: structured decision journal with safeties
        self.journal = DecisionJournal()
        self._journal_writer: JournalWriter = self.journal.writer()

        # P6C1/P6C4: External command channel with backpressure limits
        limits_cfg = self.config.get("run.external.limits", None)
        self.command_queue = CommandQueue(limits_cfg)
        self.command_queue.add_rejection_handler(self._on_command_rejection)
        self._http_server: Optional[HTTPServerHandle] = None
        http_enabled_cfg = bool(self.config.get("run.http_commands.enabled", True))
        self._http_commands_enabled = http_enabled_cfg and self.external_mode == "live"

        if self._http_commands_enabled:
            def _active_run_id() -> Optional[str]:
                return getattr(self, "run_id", None)

            try:
                self._http_server = start_http_server(
                    self.command_queue,
                    _active_run_id,
                    host="127.0.0.1",
                    port=8089,
                    version_supplier=lambda: getattr(self, "engine_version", "unknown"),
                    build_hash_supplier=lambda: self._engine_build_hash,
                )
            except Exception:
                logger.exception("Failed to start diagnostics HTTP server")

        # Phase 3 analytics scaffolding
        self._tracker: Optional[Tracker] = None
        self._tracker_session_ctx: Optional[SessionCtx] = None
        self._analytics_session_closed: bool = False

        self._init_tracker()
        self._update_outbound_from_flags(self._cli_flags_context)
        self._load_internal_rules()

    # ----- helpers -----

    def _default_mode(self) -> str:
        modes = self.spec.get("modes", {}) or {}
        if "Main" in modes:
            return "Main"
        if modes:
            return next(iter(modes.keys()))
        return "Main"

    @property
    def run_id(self) -> str:
        return getattr(self, "_run_id", "unknown")

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

    # ----- Phase 3 analytics scaffolding -----

    def _init_tracker(self) -> None:
        embed_enabled = bool(self._flags.get("embed_analytics", EMBED_ANALYTICS_DEFAULT))
        if not embed_enabled:
            self._tracker = None
            return

        run_config = self.spec.get("run") if isinstance(self.spec, dict) else {}
        try:
            tracker = Tracker(run_config)
        except Exception:
            # Fail-open: analytics scaffolding must not affect runtime behavior.
            self._tracker = None
            return

        bankroll = self._bankroll_best_effort()
        bankroll_val = float(bankroll) if bankroll is not None else 0.0
        session_ctx = SessionCtx(bankroll=bankroll_val)

        self._tracker = tracker
        self._tracker_session_ctx = session_ctx
        tracker.on_session_start(session_ctx)

    @staticmethod
    def _coerce_seed(seed_raw: Any) -> Optional[int]:
        if seed_raw is None:
            return None
        if isinstance(seed_raw, bool):
            return None
        try:
            return int(seed_raw)
        except (TypeError, ValueError):
            try:
                return int(str(seed_raw).strip())
            except Exception:
                return None

    def _apply_run_identity_from_spec(self, run_blk: Any, csv_blk: Any) -> None:
        run_id_raw = None
        seed_raw = None
        if isinstance(csv_blk, dict):
            run_id_raw = csv_blk.get("run_id")
            seed_raw = csv_blk.get("seed")
        if run_id_raw is not None:
            run_id_str = str(run_id_raw).strip()
            if run_id_str:
                self._run_id = run_id_str
        if not getattr(self, "_run_id", None):
            self._run_id = str(uuid4())
        seed_val = self._coerce_seed(seed_raw)
        if seed_val is not None:
            self._seed_value = seed_val

    @staticmethod
    def _detect_build_hash() -> str:
        try:
            root = Path(__file__).resolve().parent.parent
            result = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=root,
                stderr=subprocess.DEVNULL,
            )
            value = result.decode("utf-8").strip()
            return value or "unknown"
        except Exception:
            return "unknown"

    def _resolve_external_mode(self) -> Tuple[str, str]:
        cfg = self.config.get("run.external", None)
        mode_value: Optional[str] = None
        source = "default"
        if isinstance(cfg, str):
            mode_value = cfg
            source = "spec"
        else:
            candidate = getattr(cfg, "mode", None) if cfg is not None else None
            if candidate is not None:
                mode_value = candidate
                source = "spec"
        text = str(mode_value).strip().lower() if mode_value is not None else ""
        if text in {"off", "live", "replay"}:
            return text, source
        return "live", "default"

    def _resolve_command_tape_path(self) -> Optional[str]:
        tape_path: Optional[str] = None
        external_cfg = self.config.get("run.external", None)
        candidates = []
        if external_cfg is not None:
            for attr in ("tape_path", "command_tape_path"):
                val = getattr(external_cfg, attr, None)
                if val:
                    candidates.append(val)
        cli_val = self._cli_flags_context.get("command_tape_path") if isinstance(self._cli_flags_context, dict) else None
        if cli_val:
            candidates.insert(0, cli_val)
        for cand in candidates:
            if isinstance(cand, (str, Path)) and str(cand).strip():
                tape_path = str(cand)
                break
        if tape_path is None:
            existing = self._export_paths.get("command_tape")
            if existing:
                tape_path = str(existing)
        if tape_path is None:
            tape_path = "export/command_tape.jsonl"
        self._export_paths["command_tape"] = tape_path
        return tape_path

    def _get_command_tape(self) -> Optional[CommandTape]:
        if self.external_mode == "replay":
            return None
        path = self._command_tape_path or self._resolve_command_tape_path()
        if not path:
            return None
        if self._command_tape is None or self._command_tape_path != path:
            self._command_tape = CommandTape(path)
            self._command_tape_path = path
        return self._command_tape

    def _load_replay_tape(self) -> None:
        self._replay_commands.clear()
        path = self._command_tape_path
        if not path:
            return
        records: List[Dict[str, Any]] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(data, dict):
                        continue
                    data.setdefault("args", {})
                    data.setdefault("source", "replay")
                    records.append(data)
        except Exception:
            return

        def _num(val: Any) -> Optional[float]:
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                try:
                    return float(val)
                except Exception:
                    return None
            return None

        records.sort(
            key=lambda item: (
                0 if _num(item.get("journal_seq")) is not None else 1,
                _num(item.get("journal_seq")) or 0.0,
                0 if _num(item.get("hand_id")) is not None else 1,
                _num(item.get("hand_id")) or 0.0,
                0 if _num(item.get("roll_in_hand")) is not None else 1,
                _num(item.get("roll_in_hand")) or 0.0,
                _num(item.get("ts")) or 0.0,
            )
        )

        for record in records:
            self._replay_commands.append(record)
        if records:
            run_id = records[0].get("run_id")
            if run_id:
                self._run_id = str(run_id)

    def _enqueue_replay_command(self, payload: Dict[str, Any]) -> None:
        if not hasattr(self, "command_queue"):
            return
        corr = payload.get("correlation_id")
        if corr:
            correlation_id = str(corr)
        else:
            correlation_id = f"replay-{int(time.time()*1000)}-{len(self._replay_commands)}"
        rejection_reason = payload.get("rejection_reason")
        executed_flag = payload.get("executed")
        if executed_flag is False and rejection_reason:
            command = {
                "run_id": self.run_id,
                "action": str(payload.get("action", "")),
                "args": payload.get("args", {}) or {},
                "source": str(payload.get("source", "replay")),
                "correlation_id": correlation_id,
            }
            try:
                stats = getattr(self, "command_queue", None)
                if stats is not None:
                    stats.stats["rejected"][str(rejection_reason)] += 1
            except Exception:
                pass
            self._on_command_rejection(
                {
                    "source": command["source"],
                    "reason": str(rejection_reason),
                    "command": command,
                }
            )
            return
        command = {
            "run_id": self.run_id,
            "action": str(payload.get("action", "")),
            "args": payload.get("args", {}) or {},
            "source": str(payload.get("source", "replay")),
            "correlation_id": correlation_id,
            "_csc_replay": True,
        }
        self.command_queue.enqueue(command)

    def _inject_replay_commands(self, tracker: Optional[Tracker]) -> None:
        if self.external_mode != "replay":
            return
        current_hand = tracker.hand_id if tracker is not None else None
        current_roll = tracker.roll_in_hand if tracker is not None else None
        while self._replay_commands:
            entry = self._replay_commands[0]
            hand_target = entry.get("hand_id")
            roll_target = entry.get("roll_in_hand")
            if hand_target is not None and current_hand is not None and hand_target > current_hand:
                break
            self._replay_commands.popleft()
            self._enqueue_replay_command(entry)

    def _append_command_tape(
        self,
        *,
        source: str,
        action: str,
        args: Dict[str, Any],
        executed: bool,
        correlation_id: Optional[str],
        rejection_reason: Optional[str],
        hand_id: Optional[int],
        roll_in_hand: Optional[int],
        seq: Optional[int],
    ) -> None:
        if self.external_mode == "replay":
            return
        tape = self._get_command_tape()
        if tape is None:
            return
        tape.append(
            self.run_id,
            source,
            action,
            args,
            executed,
            correlation_id=correlation_id,
            rejection_reason=rejection_reason,
            hand_id=hand_id,
            roll_in_hand=roll_in_hand,
            seq=seq,
        )

    def _on_command_rejection(self, payload: Dict[str, Any]) -> None:
        try:
            if not isinstance(payload, dict):
                return
            command = payload.get("command") if isinstance(payload.get("command"), dict) else None
            if not command:
                return
            run_id = command.get("run_id")
            if not isinstance(run_id, str) or run_id != self.run_id:
                return
            source_label = str(payload.get("source") or command.get("source") or "external")
            action = str(command.get("action") or "unknown")
            raw_args = command.get("args")
            args = raw_args if isinstance(raw_args, dict) else {}
            corr = command.get("correlation_id")
            reason = str(payload.get("reason") or "rejected")
            tracker = getattr(self, "_tracker", None)
            hand_id = getattr(tracker, "hand_id", None)
            roll_in_hand = getattr(tracker, "roll_in_hand", None)
            entry = self.journal.record(
                {
                    "run_id": self.run_id,
                    "hand_id": hand_id,
                    "roll_in_hand": roll_in_hand,
                    "origin": f"external:{source_label}",
                    "action": action,
                    "args": args,
                    "executed": False,
                    "rejection_reason": reason,
                    "correlation_id": corr,
                }
            )
            self._append_command_tape(
                source=source_label,
                action=action,
                args=args,
                executed=False,
                correlation_id=str(corr) if corr is not None else None,
                rejection_reason=reason,
                hand_id=entry.get("hand_id"),
                roll_in_hand=entry.get("roll_in_hand"),
                seq=entry.get("seq"),
            )
        except Exception:
            logger.exception("Failed to record command rejection")

    def _webhook_base_payload(self) -> Dict[str, Any]:
        run_id = getattr(self, "_run_id", None)
        if not run_id:
            run_id = str(uuid4())
            self._run_id = run_id
        return {"run_id": run_id}

    def _emit_webhook(self, event: str, payload: Dict[str, Any]) -> None:
        if self.external_mode == "replay":
            return
        publisher = getattr(self, "webhooks", None)
        if publisher is None:
            return
        data = dict(payload)
        data.setdefault("event", event)
        publisher.emit(event, data)

    @staticmethod
    def _normalize_cli_flags(flags: Any) -> Dict[str, Any]:
        keys = (
            "demo_fallbacks",
            "demo_fallbacks_source",
            "strict",
            "strict_source",
            "embed_analytics",
            "embed_analytics_source",
            "export",
            "export_source",
            "webhook_enabled",
            "webhook_enabled_source",
            "webhook_url",
            "webhook_timeout",
            "webhook_url_source",
            "evo_enabled",
            "trial_tag",
            "command_tape_path",
        )
        if flags is None:
            return {}
        candidate: Any = flags
        if is_dataclass(candidate):
            candidate = asdict(candidate)  # type: ignore[arg-type]
        out: Dict[str, Any] = {}
        if isinstance(candidate, dict):
            for key in keys:
                if key in candidate:
                    out[key] = candidate[key]
        else:
            for key in keys:
                if hasattr(candidate, key):
                    out[key] = getattr(candidate, key)
        return out

    def _update_outbound_from_flags(self, flags: Dict[str, Any]) -> None:
        if not isinstance(flags, dict):
            flags = {}
        url_raw = flags.get("webhook_url")
        url = None
        if isinstance(url_raw, str):
            url = url_raw.strip() or None
        self._webhook_url_actual = url
        self._webhook_url_present = bool(url)

        timeout_raw = flags.get("webhook_timeout", self._webhook_timeout)
        try:
            timeout_val = float(timeout_raw)
        except (TypeError, ValueError):
            timeout_val = 2.0
        self._webhook_timeout = timeout_val

        enabled_flag = bool(flags.get("webhook_enabled", False)) and bool(url)

        source_raw = flags.get("webhook_url_source")
        if isinstance(source_raw, str) and source_raw.strip():
            source = source_raw.strip()
        else:
            source = "cli" if url else "default"
        self._webhook_url_source = source
        if isinstance(flags, dict):
            flags.setdefault("webhook_url_source", source)

        self._outbound = Outbound(enabled=enabled_flag, url=url, timeout=timeout_val)
        webhooks_enabled = getattr(getattr(self, "webhooks", None), "enabled", False)
        if (self._outbound.enabled or webhooks_enabled) and not self._outbound_run_started:
            self._emit_run_started()

    def stop(self) -> None:
        self._stop_http_server()

    def _stop_http_server(self) -> None:
        server = getattr(self, "_http_server", None)
        if server is None:
            return
        server.stop()
        self._http_server = None

    # ----- Phase 5: Internal Brain ruleset ----------------------------------

    @staticmethod
    def _copy_rule_template(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return json.loads(json.dumps(data))
        except Exception:
            return dict(data)

    @staticmethod
    def _substitute_placeholders(payload: Any, key: str, value: Any) -> Any:
        placeholder = f"${key}"
        if isinstance(payload, str):
            return payload.replace(placeholder, str(value))
        if isinstance(payload, list):
            return [ControlStrategy._substitute_placeholders(item, key, value) for item in payload]
        if isinstance(payload, dict):
            return {
                k: ControlStrategy._substitute_placeholders(v, key, value)
                for k, v in payload.items()
            }
        return payload

    def _load_internal_rules(self) -> None:
        self.ruleset: List[Dict[str, Any]] = []
        self._ruleset_errors: List[str] = []

        brain_cfg = {}
        raw_brain = self.spec.get("internal_brain") if isinstance(self.spec, dict) else None
        if isinstance(raw_brain, dict):
            brain_cfg = raw_brain

        macros_raw = brain_cfg.get("macros", {}) if isinstance(brain_cfg, dict) else {}
        rules_raw = brain_cfg.get("rules") if isinstance(brain_cfg, dict) else None

        if not isinstance(rules_raw, list) or not rules_raw:
            return

        macros: Dict[str, Dict[str, Any]] = {}
        if isinstance(macros_raw, dict):
            for name, template in macros_raw.items():
                if isinstance(template, dict):
                    macros[str(name)] = self._copy_rule_template(template)

        expanded: List[Dict[str, Any]] = []
        for idx, entry in enumerate(rules_raw, start=1):
            if not isinstance(entry, dict):
                continue

            rule_obj: Dict[str, Any]
            if "use" in entry:
                macro_name = str(entry.get("use", "")).strip()
                macro = macros.get(macro_name)
                if not macro:
                    continue
                rule_obj = self._copy_rule_template(macro)
                params = entry.get("params")
                if isinstance(params, dict):
                    for param_key, param_val in params.items():
                        rule_obj = self._substitute_placeholders(rule_obj, str(param_key), param_val)
                for key, val in entry.items():
                    if key in {"use", "params"}:
                        continue
                    rule_obj[key] = val
                if "id" not in rule_obj or not rule_obj.get("id"):
                    rule_obj["id"] = entry.get("id") or f"{macro_name}_{idx:03d}"
            else:
                rule_obj = self._copy_rule_template(entry)
                if "id" not in rule_obj or not rule_obj.get("id"):
                    rule_obj["id"] = f"rule_{idx:03d}"

            rule_obj.setdefault("enabled", True)
            expanded.append(rule_obj)

        if not expanded:
            return

        errors = validate_ruleset(expanded)
        self._ruleset_errors = errors
        self.ruleset = expanded

    def _emit_run_started(self) -> None:
        if self._outbound_run_started:
            return
        spec_path = self._spec_path or ""
        manifest_hint = self._export_paths.get("manifest", "export/manifest.json")
        payload = {**self._webhook_base_payload(), "spec": spec_path, "manifest_path": manifest_hint}
        seed_val = self._seed_value
        if seed_val is not None:
            payload["seed"] = seed_val
        if self._outbound.enabled:
            self._outbound.emit("run.started", payload)
        self._emit_webhook("run.started", payload)
        self._outbound_run_started = True

    def _emit_run_finished(self, report: Dict[str, Any]) -> None:
        if self._outbound_run_finished:
            return
        payload = {
            **self._webhook_base_payload(),
            "summary_schema_version": report.get("summary_schema_version"),
            "journal_schema_version": report.get("journal_schema_version"),
        }
        if self._outbound.enabled:
            self._outbound.emit("run.finished", payload)
        self._emit_webhook("run.finished", payload)
        self._outbound_run_finished = True

    def _analytics_start_hand(self, point_value: Optional[int] = None) -> None:
        tracker = self._tracker
        if tracker is None:
            return

        hand_id = tracker.hand_id + 1
        hand_ctx = HandCtx(hand_id=hand_id, point=point_value)
        tracker.on_hand_start(hand_ctx)
        payload = {**self._webhook_base_payload(), "hand_id": hand_id}
        if point_value is not None:
            payload["point"] = point_value
        if self._outbound.enabled:
            self._outbound.emit("hand.started", payload)
        self._emit_webhook("hand.started", payload)

    @staticmethod
    def _analytics_to_float(val: Any) -> Optional[float]:
        if isinstance(val, (int, float)):
            return float(val)
        try:
            return float(str(val))
        except Exception:
            return None

    def _analytics_record_roll(self, event: Dict[str, Any]) -> None:
        tracker = self._tracker
        if tracker is None:
            return

        if tracker.hand_id == 0:
            self._analytics_start_hand(point_value=None)

        # Decrement per-roll cooldowns before evaluating new decisions.
        if hasattr(self, "journal"):
            self.journal.tick()

        bankroll_before = self._analytics_to_float(event.get("bankroll_before"))
        bankroll_after = self._analytics_to_float(event.get("bankroll_after"))
        bankroll_value = self._analytics_to_float(event.get("bankroll"))
        delta = self._analytics_to_float(event.get("bankroll_delta"))
        if delta is None:
            delta = self._analytics_to_float(event.get("delta"))
        if delta is None:
            delta = self._analytics_to_float(event.get("payout"))

        if bankroll_after is None and bankroll_value is not None:
            bankroll_after = bankroll_value

        if bankroll_before is None:
            bankroll_before = tracker.bankroll

        if delta is None:
            if bankroll_after is not None and bankroll_before is not None:
                delta = bankroll_after - bankroll_before
            else:
                delta = 0.0

        if bankroll_after is None and bankroll_before is not None:
            bankroll_after = bankroll_before + delta

        event_type = str(event.get("type") or event.get("event") or "")
        point_raw = event.get("point")
        point_value: int | None = None
        if isinstance(point_raw, int) and not isinstance(point_raw, bool):
            point_value = point_raw
        else:
            try:
                point_value = int(point_raw) if point_raw is not None else None
            except Exception:
                point_value = None
        point_on = event.get("point_on")

        total: Any = None
        roll_ctx = RollCtx(
            hand_id=tracker.hand_id,
            roll_number=self.rolls_since_point,
            bankroll_before=bankroll_before if bankroll_before is not None else 0.0,
            delta=delta,
            event_type=event_type,
            point=point_value,
            point_on=bool(point_on),
        )
        tracker.on_roll(roll_ctx)

        try:
            snap = tracker.get_roll_snapshot()
        except Exception:
            snap = {}

        # Ensure tracker mirrors the resolved bankroll when provided explicitly.
        if bankroll_after is not None:
            tracker.bankroll = bankroll_after
            tracker.bankroll_peak = max(tracker.bankroll_peak, tracker.bankroll)
            tracker.bankroll_low = min(tracker.bankroll_low, tracker.bankroll)
            tracker.max_drawdown = max(
                tracker.max_drawdown,
                tracker.bankroll_peak - tracker.bankroll,
            )
        ruleset = getattr(self, "ruleset", None)
        if tracker is not None and isinstance(ruleset, list) and ruleset:
            ctx: Dict[str, Any] = {
                "bankroll_after": tracker.bankroll,
                "drawdown_after": tracker.bankroll_peak - tracker.bankroll,
                "hand_id": tracker.hand_id,
                "roll_in_hand": tracker.roll_in_hand,
                "point_on": bool(event.get("point_on")) if isinstance(event, dict) else bool(self.point),
            }
            total: Any = None
            if isinstance(event, dict):
                roll_info = event.get("roll")
                if isinstance(roll_info, dict):
                    total = roll_info.get("total")
                if total is None:
                    total = event.get("total")
                box_hits = event.get("box_hits")
                if isinstance(box_hits, (list, tuple, dict)):
                    ctx["box_hits"] = box_hits
                for key in ("dc_losses", "dc_wins"):
                    val = event.get(key)
                    if isinstance(val, (int, float)):
                        ctx[key] = val
                    elif isinstance(val, str):
                        try:
                            ctx[key] = float(val)
                        except ValueError:
                            continue
            if "box_hits" not in ctx:
                ctx["box_hits"] = 0
            if isinstance(total, (int, float)):
                ctx["last_roll_total"] = total
            fired_rules: List[Dict[str, Any]] = []
            decisions: List[Dict[str, Any]] = []
            try:
                results = evaluate_rules(ruleset, ctx)
            except Exception:
                results = []
            if results:
                rule_lookup: Dict[str, Dict[str, Any]] = {}
                if isinstance(ruleset, list):
                    rule_lookup = {
                        str(rule.get("id")): rule
                        for rule in ruleset
                        if isinstance(rule, dict) and rule.get("id") is not None
                    }
                for record in results:
                    decision = dict(record)
                    rid = decision.get("rule_id")
                    rule_def = rule_lookup.get(str(rid)) if rid is not None else None
                    if rule_def is not None:
                        decision["action"] = rule_def.get("action", "")
                    decisions.append(decision)
                    if decision.get("fired"):
                        fired_rules.append(decision)
                try:
                    with open("decision_candidates.jsonl", "a", encoding="utf-8") as f:
                        for record in decisions:
                            f.write(json.dumps(record) + "\n")
                except Exception:
                    pass

            if fired_rules:
                current_state: Dict[str, Any] = {
                    "resolving": bool((event or {}).get("resolving")),
                    "point_on": bool(ctx.get("point_on")),
                    "roll_in_hand": ctx.get("roll_in_hand"),
                }
                runtime: Dict[str, Any] = {
                    "tracker": tracker,
                    "state": current_state,
                    "context": dict(ctx),
                }
                verbs_executed: set[str] = set()
                for decision in fired_rules:
                    action_str = str(decision.get("action") or "")
                    if not action_str:
                        continue
                    verb = action_str.split("(")[0]
                    act = ACTIONS.get(verb)
                    if not act:
                        continue

                    rule_id_raw = decision.get("rule_id")
                    if rule_id_raw is None:
                        continue
                    rule_id = str(rule_id_raw)
                    decision["rule_id"] = rule_id

                    scope = str(decision.get("scope") or "roll")
                    cooldown_raw = decision.get("cooldown", 0)
                    try:
                        cooldown = int(cooldown_raw)
                    except (TypeError, ValueError):
                        cooldown = 0
                    decision["cooldown"] = cooldown
                    decision["cooldown_remaining"] = self.journal.cooldowns.get(rule_id, 0)

                    allowed, reason = self.journal.can_fire(rule_id, scope, cooldown)
                    decision["cooldown_allowed"] = allowed
                    decision["cooldown_reason"] = reason

                    legal, timing_reason = is_legal_timing(current_state, {"verb": verb})
                    decision["timing_legal"] = legal
                    decision["timing_reason"] = timing_reason

                    duplicate_blocked = False
                    executed = False
                    result: Any = None

                    if allowed and legal:
                        if verb in verbs_executed:
                            duplicate_blocked = True
                        else:
                            result = act.execute(runtime, decision)
                            executed = True
                            verbs_executed.add(verb)
                            self.journal.apply_fire(rule_id, scope, cooldown)
                            decision["cooldown_remaining"] = self.journal.cooldowns.get(rule_id, 0)
                    decision["duplicate_blocked"] = duplicate_blocked

                    if executed:
                        decision["executed"] = True
                        decision["result"] = result
                    else:
                        decision["executed"] = False
                        rejection_reason = None
                        if duplicate_blocked:
                            decision["note"] = "duplicate_blocked"
                            rejection_reason = "duplicate_blocked"
                        elif not allowed:
                            decision["note"] = reason
                            rejection_reason = str(reason)
                        elif not legal:
                            decision["note"] = timing_reason
                            rejection_reason = str(timing_reason)
                        decision["rejection_reason"] = rejection_reason

                    decision["run_id"] = self.run_id
                    decision["origin"] = f"rule:{rule_id}"
                    args_payload = decision.get("args")
                    if not isinstance(args_payload, dict):
                        args_payload = {}
                    self._journal_writer.write(
                        run_id=self.run_id,
                        origin=f"rule:{rule_id}",
                        action=verb,
                        args=args_payload,
                        executed=bool(decision.get("executed")),
                        rejection_reason=decision.get("rejection_reason"),
                        extra=dict(decision),
                    )
        payload = {
            **self._webhook_base_payload(),
            "hand_id": snap.get("hand_id") if isinstance(snap, dict) else None,
            "roll_in_hand": snap.get("roll_in_hand") if isinstance(snap, dict) else None,
        }
        if self._outbound.enabled:
            self._outbound.emit("roll.processed", payload)
        roll_payload = dict(payload)
        roll_payload.update({
            "bankroll_before": bankroll_before,
            "bankroll_after": bankroll_after,
            "bankroll_delta": delta,
            "event_type": event_type,
            "point": point_value,
            "point_on": bool(point_on),
        })
        if isinstance(total, (int, float)):
            roll_payload["last_roll_total"] = total
        self._emit_webhook("roll.processed", roll_payload)

    def _analytics_end_hand(self, point_value: Optional[int]) -> None:
        tracker = self._tracker
        if tracker is None or tracker.hand_id == 0:
            return

        hand_id = tracker.hand_id
        hand_ctx = HandCtx(hand_id=hand_id, point=point_value)
        tracker.on_hand_end(hand_ctx)
        payload = {**self._webhook_base_payload(), "hand_id": hand_id}
        if point_value is not None:
            payload["point"] = point_value
        if self._outbound.enabled:
            self._outbound.emit("hand.finished", payload)
        self._emit_webhook("hand.finished", payload)

    def _analytics_session_end(self) -> None:
        tracker = self._tracker
        if tracker is None or self._analytics_session_closed:
            return

        session_ctx = SessionCtx(bankroll=tracker.bankroll)
        self._tracker_session_ctx = session_ctx
        tracker.on_session_end(session_ctx)
        self._analytics_session_closed = True

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
        run_id_raw = csv_cfg.get("run_id")
        if run_id_raw is not None:
            run_id_str = str(run_id_raw).strip()
            if run_id_str:
                self._run_id = run_id_str
        run_id = self._run_id
        seed_val = self._coerce_seed(csv_cfg.get("seed"))
        if seed_val is not None:
            self._seed_value = seed_val
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
            analytics_cols = None
            if self._tracker is not None:
                analytics_cols = [
                    "hand_id",
                    "roll_in_hand",
                    "bankroll_after",
                    "drawdown_after",
                ]
            j = CSVJournal(
                cfg["path"],
                append=cfg["append"],
                run_id=cfg.get("run_id"),
                seed=cfg.get("seed"),
                analytics_columns=analytics_cols,
            )
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
        if self._tracker is not None:
            snap.update(self._tracker.get_roll_snapshot())
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
            self._analytics_start_hand(point_value=None)
            self.point = None
            self.rolls_since_point = 0
            self.on_comeout = True

            self._analytics_record_roll(event)

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

            self._analytics_record_roll(event)

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

            self._analytics_record_roll(event)

            current_state = self._current_state_for_eval()
            tracker = self._tracker
            self._inject_replay_commands(tracker)
            pending = list(self.command_queue.drain()) if hasattr(self, "command_queue") else []
            seen_this_roll = set()
            for cmd in pending:
                cmd.pop("_csc_replay", None)
                verb = cmd["action"]
                raw_args = cmd.get("args")
                args = raw_args if isinstance(raw_args, dict) else {}
                source_label = str(cmd.get("source", "external"))
                origin = f"external:{source_label}"
                corr = cmd.get("correlation_id")
                key = (
                    origin,
                    verb,
                    json.dumps(args, sort_keys=True),
                )
                if key in seen_this_roll:
                    rejection_reason = "duplicate_roll"
                    record = {
                        "run_id": self.run_id,
                        "hand_id": tracker.hand_id if tracker is not None else None,
                        "roll_in_hand": tracker.roll_in_hand if tracker is not None else None,
                        "origin": origin,
                        "action": verb,
                        "args": args,
                        "executed": False,
                        "rejection_reason": rejection_reason,
                        "correlation_id": str(corr) if corr is not None else None,
                    }
                    outcome = self.command_queue.record_outcome(
                        source_label,
                        executed=False,
                        rejection_reason=rejection_reason,
                    )
                    if outcome.get("circuit_breaker_reset"):
                        record["circuit_breaker_reset"] = True
                    entry = self.journal.record(record)
                    self._append_command_tape(
                        source=source_label,
                        action=verb,
                        args=args,
                        executed=False,
                        correlation_id=str(corr) if corr is not None else None,
                        rejection_reason=rejection_reason,
                        hand_id=entry.get("hand_id"),
                        roll_in_hand=entry.get("roll_in_hand"),
                        seq=entry.get("seq") if isinstance(entry, dict) else None,
                    )
                    continue
                seen_this_roll.add(key)
                legal, reason = is_legal_timing(current_state, {"verb": verb})
                rejection_reason = None
                record = {
                    "run_id": self.run_id,
                    "hand_id": tracker.hand_id if tracker is not None else None,
                    "roll_in_hand": tracker.roll_in_hand if tracker is not None else None,
                    "action": verb,
                    "args": args,
                    "origin": origin,
                    "correlation_id": corr,
                    "timing_legal": legal,
                    "timing_reason": reason,
                }
                executed = False
                result: Any = None
                if not legal:
                    rejection_reason = f"timing:{reason}"
                    record["rejection_reason"] = rejection_reason
                else:
                    result = ACTIONS[verb].execute(self.__dict__, {"args": args})
                    executed = True
                    record["result"] = result
                record["executed"] = executed
                outcome = self.command_queue.record_outcome(
                    source_label,
                    executed=executed,
                    rejection_reason=rejection_reason,
                )
                if outcome.get("circuit_breaker_reset"):
                    record["circuit_breaker_reset"] = True
                entry = self._journal_writer.write(
                    run_id=self.run_id,
                    origin=origin,
                    action=verb,
                    args=args,
                    executed=executed,
                    rejection_reason=rejection_reason,
                    correlation_id=str(corr) if corr is not None else None,
                    extra=record,
                )
                self._append_command_tape(
                    source=source_label,
                    action=verb,
                    args=args,
                    executed=executed,
                    correlation_id=str(corr) if corr is not None else None,
                    rejection_reason=rejection_reason,
                    hand_id=record["hand_id"],
                    roll_in_hand=record["roll_in_hand"],
                    seq=entry.get("seq") if isinstance(entry, dict) else None,
                )

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
            point_before = self.point
            self._analytics_record_roll(event)
            self._analytics_end_hand(point_before)
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

    def generate_report(
        self,
        report_path: Optional[str | Path] = None,
        *,
        spec_path: Optional[str | Path] = None,
        cli_flags: Optional[Any] = None,
        export_paths: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Build a run report JSON and return it as a dict.
        Prefers meta.json for identity/memory if present; otherwise falls back to
        in-memory controller state and CSV config. If a path is configured, also writes it.
        """
        if spec_path is not None:
            self._spec_path = str(spec_path)

        cli_flags_dict: Dict[str, Any] = dict(self._cli_flags_context)
        if cli_flags is not None:
            normalized = self._normalize_cli_flags(cli_flags)
            if normalized:
                cli_flags_dict.update(normalized)
        self._cli_flags_context = dict(cli_flags_dict)
        self._update_outbound_from_flags(self._cli_flags_context)

        resolved_export_paths: Dict[str, Optional[str]] = {}
        if export_paths is not None:
            resolved_export_paths.update(
                {
                    str(k): (str(v) if v is not None else None)
                    for k, v in export_paths.items()
                }
            )
        elif isinstance(self._export_paths, dict):
            resolved_export_paths.update(self._export_paths)

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
        run_id_from_identity = identity.get("run_id")
        if run_id_from_identity:
            self._run_id = str(run_id_from_identity)
        elif getattr(self, "_run_id", None):
            identity["run_id"] = self._run_id
        else:
            self._run_id = str(uuid4())
            identity["run_id"] = self._run_id
        seed_from_identity = identity.get("seed")
        if seed_from_identity is not None:
            self._seed_value = seed_from_identity
        elif self._seed_value is not None:
            identity["seed"] = self._seed_value
        if not memory:
            memory = dict(self.memory)

        self._analytics_session_end()

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

        csv_source = source_files.get("csv")
        if csv_source:
            resolved_export_paths["journal"] = str(csv_source)

        run_flag_values = {
            "demo_fallbacks": bool(self._flags.get("demo_fallbacks", False)),
            "strict": bool(self._flags.get("strict", False)),
            "embed_analytics": bool(
                self._flags.get("embed_analytics", EMBED_ANALYTICS_DEFAULT)
            ),
        }

        run_flags = dict(run_flag_values)
        run_flags["export"] = bool(cli_flags_dict.get("export", False))
        webhook_enabled = bool(self._outbound.enabled)
        run_flags["webhook_enabled"] = webhook_enabled
        run_flags["webhook_timeout"] = float(self._webhook_timeout)
        run_flags["webhook_url_source"] = self._webhook_url_source
        run_flags["webhook_url"] = bool(self._webhook_url_present)
        run_flags["evo_enabled"] = bool(cli_flags_dict.get("evo_enabled", False))
        run_flags["trial_tag"] = cli_flags_dict.get("trial_tag")
        run_flags["external_mode"] = self.external_mode
        run_flags["demo_fallbacks_source"] = self._flag_sources.get("demo_fallbacks", "default")
        run_flags["strict_source"] = self._flag_sources.get("strict", "default")
        run_flags["embed_analytics_source"] = self._flag_sources.get("embed_analytics", "default")
        run_flags["export_source"] = str(cli_flags_dict.get("export_source", "default"))
        run_flags["webhook_enabled_source"] = str(
            cli_flags_dict.get("webhook_enabled_source", "default")
        )
        run_flags["evo_enabled_source"] = str(
            cli_flags_dict.get("evo_enabled_source", "default")
        )
        run_flags["trial_tag_source"] = str(cli_flags_dict.get("trial_tag_source", "default"))
        run_flags["external_mode_source"] = self._external_mode_source

        run_flag_sources_meta = dict(self._flag_sources)
        run_flag_sources_meta["export"] = run_flags["export_source"]
        run_flag_sources_meta["webhook_enabled"] = run_flags["webhook_enabled_source"]
        run_flag_sources_meta["evo_enabled"] = run_flags["evo_enabled_source"]
        run_flag_sources_meta["trial_tag"] = run_flags["trial_tag_source"]
        run_flag_sources_meta["external_mode"] = self._external_mode_source

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
                "validation_engine": VALIDATION_ENGINE_VERSION,
                "run_flags": {
                    "values": run_flag_values,
                    "sources": run_flag_sources_meta,
                },
            },
        }

        run_flags_meta = report["metadata"].setdefault("run_flags", {})
        run_flags_meta.update(
            {
                "values": run_flag_values,
                "sources": run_flag_sources_meta,
                "webhook_enabled": webhook_enabled,
                "webhook_url_source": self._webhook_url_source,
                "webhook_url_masked": bool(self._webhook_url_present),
            }
        )
        run_flags_meta["external_mode"] = self.external_mode
        def _source_for(key: str, default: str = "default") -> str:
            src = run_flags.get(f"{key}_source")
            if isinstance(src, str) and src:
                return src
            if key in run_flag_sources_meta and run_flag_sources_meta[key]:
                return str(run_flag_sources_meta[key])
            return default

        for key in ["strict", "demo_fallbacks", "embed_analytics", "export", "webhook_enabled", "external_mode"]:
            if key in run_flags or key in run_flags_meta:
                run_flags_meta[f"{key}_source"] = _source_for(key)

        meta = report.setdefault("metadata", {})
        existing_deprecations = meta.get("deprecations")
        if isinstance(existing_deprecations, list):
            deprecations_out = list(existing_deprecations)
        else:
            deprecations_out = []

        for entry in self._spec_deprecations:
            if isinstance(entry, dict) and entry not in deprecations_out:
                deprecations_out.append(entry)

        meta["deprecations"] = deprecations_out

        if hasattr(self, "command_queue") and self.command_queue is not None:
            limits = getattr(self.command_queue, "limits", {}) or {}
            stats = getattr(self.command_queue, "stats", {}) or {}

            def _plain(val: Any) -> Any:
                if isinstance(val, dict):
                    return {k: _plain(v) for k, v in val.items()}
                return val

            rejected_map = stats.get("rejected", {}) or {}
            if isinstance(rejected_map, dict):
                rejected_out = {str(k): int(v) for k, v in rejected_map.items()}
            else:
                rejected_out = {}

            queue_stats = {
                "enqueued": int(stats.get("enqueued", 0)),
                "executed": int(stats.get("executed", 0)),
                "rejected": rejected_out,
            }

            report["metadata"]["limits"] = {
                "queue_max_depth": limits.get("queue_max_depth"),
                "per_source_quota": limits.get("per_source_quota"),
                "rate": _plain(limits.get("rate", {})),
                "circuit_breaker": _plain(limits.get("circuit_breaker", {})),
                "stats": queue_stats,
            }

        # Keep the old csv.path hint too (legacy/compat)
        try:
            report["csv"] = {"path": str(getattr(j, "path")) if j is not None else None}
        except Exception:
            report["csv"] = {"path": None}

        tracker = self._tracker
        summary_block = report.setdefault("summary", {})
        if tracker is not None:
            try:
                summary_block.update(tracker.get_summary_snapshot())
            except Exception:
                pass

        bankroll_final: float = 0.0
        hands_played: int = 0
        if tracker is not None:
            try:
                bankroll_final = float(getattr(tracker, "bankroll", 0.0))
            except Exception:
                bankroll_final = 0.0
            try:
                hands_played = int(getattr(tracker, "total_hands", 0))
            except Exception:
                hands_played = 0

        journal_lines = 0
        external_executed = 0
        external_rejected = 0
        journal_path = getattr(getattr(self, "journal", None), "path", None)
        if isinstance(journal_path, (str, Path)) and str(journal_path):
            try:
                for line in Path(journal_path).read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    journal_lines += 1
                    try:
                        entry = json.loads(line)
                    except Exception:
                        continue
                    origin = str(entry.get("origin") or "")
                    if origin.startswith("external:"):
                        if entry.get("executed"):
                            external_executed += 1
                        else:
                            external_rejected += 1
            except Exception:
                pass

        if not hands_played:
            existing_total_hands = summary_block.get("total_hands")
            if isinstance(existing_total_hands, (int, float)):
                try:
                    hands_played = int(existing_total_hands)
                except Exception:
                    hands_played = 0

        summary_block["bankroll_final"] = bankroll_final
        summary_block["hands_played"] = hands_played
        summary_block["journal_lines"] = journal_lines
        summary_block["external_executed"] = external_executed
        summary_block["external_rejected"] = external_rejected

        limits_stats = ((report.get("metadata") or {}).get("limits", {}) or {}).get("stats", {})
        rejected_map = {}
        if isinstance(limits_stats, dict):
            rejected_map = limits_stats.get("rejected", {}) or {}
        total_rejections = 0
        if isinstance(rejected_map, dict):
            for value in rejected_map.values():
                try:
                    total_rejections += int(value)
                except Exception:
                    continue
        summary_block["rejections_total"] = total_rejections

        report["journal_schema_version"] = JOURNAL_SCHEMA_VERSION
        report["summary_schema_version"] = SUMMARY_SCHEMA_VERSION

        report_file: Optional[Path] = None
        if isinstance(report_path, (str, Path)) and str(report_path):
            report_file = Path(report_path)
            report_file.parent.mkdir(parents=True, exist_ok=True)
            resolved_export_paths["report"] = str(report_file)

        spec_file_value: Optional[str] = self._spec_path
        if spec_file_value is None and isinstance(self.spec, dict):
            raw_spec = self.spec.get("_csc_spec_path")
            if isinstance(raw_spec, (str, Path)):
                spec_file_value = str(raw_spec)
        if spec_file_value is None:
            spec_file_value = ""

        outputs = {
            "journal": resolved_export_paths.get("journal"),
            "report": resolved_export_paths.get("report"),
            "manifest": resolved_export_paths.get("manifest", "export/manifest.json"),
            "command_tape": resolved_export_paths.get("command_tape"),
        }

        manifest_path_str = outputs["manifest"]
        if manifest_path_str is None:
            manifest_path_str = "export/manifest.json"
            outputs["manifest"] = manifest_path_str
        resolved_export_paths["manifest"] = manifest_path_str
        manifest_path = Path(manifest_path_str)
        try:
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        bridge = EvoBridge(enabled=run_flags.get("evo_enabled", False))
        manifest: Dict[str, Any] | None = None

        try:
            manifest = generate_manifest(
                spec_file_value,
                run_flags,
                outputs,
                engine_version=self.engine_version,
                run_id=self._run_id,
            )
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
        except Exception:
            pass

        try:
            if manifest is not None:
                bridge.announce_run(manifest)
                if run_flags.get("trial_tag"):
                    bridge.tag_trial(manifest, run_flags["trial_tag"])
        except Exception:
            pass

        manifest_run_id = None
        if "manifest" in locals() and isinstance(manifest, dict):
            manifest_run_id = manifest.get("run_id")
        if manifest_run_id:
            self._run_id = str(manifest_run_id)
        report_run_id = str(manifest_run_id) if manifest_run_id else str(self._run_id)
        report["run_id"] = report_run_id

        manifest_path_value = resolved_export_paths.get("manifest") or "export/manifest.json"
        report["manifest_path"] = manifest_path_value
        report["journal_schema_version"] = JOURNAL_SCHEMA_VERSION
        report["summary_schema_version"] = SUMMARY_SCHEMA_VERSION

        metadata_block = report.setdefault("metadata", {})
        metadata_block["engine"] = {
            "name": "CrapsSim-Control",
            "version": getattr(self, "engine_version", "unknown"),
            "python": platform.python_version(),
        }
        metadata_block["artifacts"] = {
            "journal": resolved_export_paths.get("journal"),
            "report": resolved_export_paths.get("report"),
            "manifest": resolved_export_paths.get("manifest"),
            "command_tape": resolved_export_paths.get("command_tape"),
        }

        run_flags_meta_final = metadata_block.setdefault("run_flags", {})
        run_flags_meta_final.setdefault("values", run_flag_values)
        run_flags_meta_final.setdefault("sources", run_flag_sources_meta)
        run_flags_meta_final.setdefault("webhook_enabled", webhook_enabled)
        run_flags_meta_final.setdefault("webhook_url_source", self._webhook_url_source)
        run_flags_meta_final["webhook_url_masked"] = bool(run_flags.get("webhook_url"))
        run_flags_meta_final["external_mode"] = self.external_mode

        def _source_for_contract(key: str, default: str = "default") -> str:
            src = run_flags.get(f"{key}_source")
            if isinstance(src, str) and src:
                return src
            existing = run_flags_meta_final.get(f"{key}_source")
            if isinstance(existing, str) and existing:
                return existing
            return default

        for key in (
            "strict",
            "demo_fallbacks",
            "embed_analytics",
            "export",
            "webhook_enabled",
            "evo_enabled",
            "trial_tag",
            "external_mode",
        ):
            if key in run_flags or key in run_flags_meta_final:
                run_flags_meta_final[f"{key}_source"] = _source_for_contract(key)
        if report_file is not None:
            try:
                report_file.write_text(
                    json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                    encoding="utf-8",
                )
            except Exception:
                pass
        self._export_paths = dict(resolved_export_paths)
        if "command_tape" in self._export_paths:
            self._command_tape_path = self._export_paths.get("command_tape")

        self._emit_run_finished(report)

        try:
            bridge.record_result(report.get("summary", {}))
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
        tape_path = Path(self._command_tape_path) if self._command_tape_path else None

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
            else:
                artifacts.setdefault("report", None)
                fingerprints.setdefault("report", None)
            if tape_path and tape_path.exists():
                dst, _copied, fp = self._export_copy(tape_path, dest_dir, versioning=True)
                artifacts["command_tape"] = str(dst.relative_to(dest_dir))
                fingerprints["command_tape"] = fp
            else:
                artifacts.setdefault("command_tape", None)
                fingerprints.setdefault("command_tape", None)

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
            else:
                artifacts_zip.setdefault("report", None)
            if tape_path and tape_path.exists():
                zf.write(tape_path, arcname="command_tape.jsonl")
                artifacts_zip["command_tape"] = "command_tape.jsonl"
            else:
                artifacts_zip.setdefault("command_tape", None)

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

        self._stop_http_server()
        self._analytics_session_end()

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