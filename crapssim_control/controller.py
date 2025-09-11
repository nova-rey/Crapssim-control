# crapssim_control/controller.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .rules import VarStore, run_rules_for_event
from .materialize import apply_intents
from .events import derive_event  # kept available for engines that call tick() with raw table deltas


class ControlStrategy:
    """
    CrapsSim-compatible strategy that interprets a JSON spec.

    - Consumes spec: variables, modes, templates, rules, table config
    - Derives + runs rules on events (either provided by engine or via derive_event)
    - Emits bet intents and materializes them on this player using CrapsSim bet objects
    - Optionally logs per-event telemetry to CSV via Telemetry
    """

    # ---- minimal CrapsSim player surface ----
    bets: List[Any]  # list of bet objects (duck-typed)

    def __init__(
        self,
        spec: Dict[str, Any],
        *,
        telemetry: Any | None = None,
        odds_policy: str | int | None = None,
    ):
        self.spec = spec or {}
        self.vars = VarStore.from_spec(self.spec)
        self.bets = []

        # odds policy: prefer explicit arg, else spec.table.odds_policy, else default 3-4-5x
        table_cfg = (self.spec.get("table") or {})
        self.odds_policy = (
            odds_policy
            if odds_policy is not None
            else table_cfg.get("odds_policy", "3-4-5x")
        )

        # system fields (mirrors what tests & helpers expect)
        self.state: Dict[str, Any] = {
            "hand_id": 0,
            "shooter_id": 0,
            "roll_index": 0,
            "is_comeout": True,
            "point_number": None,
            "last_dice": None,          # (d1, d2)
            "bankroll": 0.0,
            "bankroll_delta": 0.0,
        }

        # set system table params for legalization etc.
        # (these may be updated again when table attaches)
        self.vars.system = {
            "bubble": bool(table_cfg.get("bubble", False)),
            "table_level": int(table_cfg.get("level", 10)),
        }

        self.table = None  # set by engine when added
        self.telemetry = telemetry

        # When no rules/modes specified, behave like static: v1 parity
        # (handled naturally by run_rules_for_event + apply_template actions)

    # ---- CrapsSim integration helpers ----

    def set_table_context(self, table: Any) -> None:
        """
        Called by engine when the player is added to the table (or you can call manually).
        We read bubble + table min for consistent legalization.
        """
        self.table = table
        try:
            bubble = bool(getattr(table, "bubble", self.vars.system["bubble"]))
            level = int(getattr(table, "level", self.vars.system["table_level"]))
            self.vars.system["bubble"] = bubble
            self.vars.system["table_level"] = level
        except Exception:
            pass

    # Some engines call player.attach(table) or similar; alias to our setter.
    attach = set_table_context

    # ---- Event/roll entrypoints ----

    def on_event(self, event: Dict[str, Any]) -> None:
        """
        Primary entrypoint: feed an already-derived event dict, run rules, apply bets.
        Event example: {"event":"comeout"} or {"event":"bet_resolved","bet":"pass","result":"lose"}
        """
        # 1) Maintain light state for telemetry and simple rules that inspect current table-ish values
        self._ingest_event_for_state(event)

        # 2) Execute rules → intents
        intents = run_rules_for_event(self.spec, self.vars, event)

        # 3) (optional) Telemetry BEFORE materialize (what we intend to do)
        if self.telemetry:
            self._emit_telemetry(event, intents)

        # 4) Materialize intents to our bets list / underlying engine
        apply_intents(self, intents, odds_policy=self.odds_policy)

        # 5) Nothing to return; the table/engine will continue rolling

    def tick(self, table_snapshot_before: Dict[str, Any], table_snapshot_after: Dict[str, Any]) -> None:
        """
        Alternate entrypoint: derive the event from two table snapshots.
        Useful if the engine cannot or does not emit semantic events.
        """
        ev = derive_event(table_snapshot_before, table_snapshot_after)
        self.on_event(ev)

    # ---- Public helpers used by tests and higher layers ----

    def set_bankroll(self, bankroll: float) -> None:
        """Update absolute bankroll; delta is computed from last known value."""
        prev = float(self.state.get("bankroll", 0.0))
        self.state["bankroll"] = float(bankroll)
        self.state["bankroll_delta"] = float(bankroll) - prev

    def note_roll(self, d1: int, d2: int) -> None:
        """Optionally called by host engine to record dice for telemetry/rules that care."""
        self.state["last_dice"] = (int(d1), int(d2))
        self.state["roll_index"] = int(self.state.get("roll_index", 0)) + 1

    def set_point(self, point_number: Optional[int]) -> None:
        """Optionally called by host engine when point changes."""
        self.state["point_number"] = int(point_number) if point_number else None
        self.state["is_comeout"] = point_number is None

    # ---- Internal state/telemetry helpers ----

    def _ingest_event_for_state(self, event: Dict[str, Any]) -> None:
        etype = event.get("event")
        if etype == "comeout":
            self.state["is_comeout"] = True
            self.state["roll_index"] = 0
        elif etype == "point_established":
            # event may include {"point": 6}
            p = event.get("point")
            self.state["point_number"] = p
            self.state["is_comeout"] = False
            self.state["roll_index"] = 0
        elif etype == "point_made":
            self.state["point_number"] = None
            self.state["is_comeout"] = True
        elif etype == "seven_out":
            self.state["point_number"] = None
            self.state["is_comeout"] = True
        elif etype == "roll":
            # optional dice info
            d = event.get("dice")
            if isinstance(d, (list, tuple)) and len(d) == 2:
                self.state["last_dice"] = (int(d[0]), int(d[1]))
            self.state["roll_index"] = int(self.state.get("roll_index", 0)) + 1
        elif etype == "shooter_change":
            self.state["shooter_id"] = int(self.state.get("shooter_id", 0)) + 1
            self.state["hand_id"] = int(self.state.get("hand_id", 0)) + 1
            self.state["roll_index"] = 0

        # bank deltas might be set externally; if not, keep last delta as-is

        # Keep system params synced from table if available
        if self.table is not None:
            try:
                self.vars.system["bubble"] = bool(getattr(self.table, "bubble", self.vars.system["bubble"]))
                # prefer "level" attr if present (CrapsSim), fall back to table_min/table_level
                lvl = getattr(self.table, "level", None)
                if lvl is None:
                    lvl = getattr(self.table, "table_min", None)
                if lvl is None:
                    lvl = self.vars.system["table_level"]
                self.vars.system["table_level"] = int(lvl)
            except Exception:
                pass

    def _emit_telemetry(self, event: Dict[str, Any], intents: List[Any]) -> None:
        # build a shallow snapshot for logger
        table_state = {
            "hand_id": self.state.get("hand_id"),
            "shooter_id": self.state.get("shooter_id"),
            "roll_index": self.state.get("roll_index"),
            "phase": "comeout" if self.state.get("is_comeout") else "point",
            "point": self.state.get("point_number"),
            "dice": self.state.get("last_dice"),
        }
        bankroll = self.state.get("bankroll")
        bankroll_delta = self.state.get("bankroll_delta")
        mode = None
        vars_snapshot = {}
        try:
            mode = self.vars.user.get("mode")
            vars_snapshot = dict(self.vars.user)
        except Exception:
            pass

        try:
            self.telemetry.log_tick(
                event=event,
                table_state=table_state,
                bankroll=bankroll,
                bankroll_delta=bankroll_delta,
                mode=mode,
                vars_snapshot=vars_snapshot,
                intents=intents,
            )
        except Exception:
            # Never let logging break the sim
            pass