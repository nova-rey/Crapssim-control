from __future__ import annotations

from typing import Any, Dict, Optional, Tuple, List

from .templates import render_template
from .events import derive_event
from .varstore import VarStore
from .rules import run_rules_for_event
from .materialize import apply_intents
from .telemetry import Telemetry


class ControlStrategy:
    """
    Wraps a strategy spec and exposes a small API the engine adapter can call:
      - update_bets(table): derive event -> run rules -> render/apply intents
    """

    def __init__(
        self,
        spec: Dict[str, Any],
        telemetry: Optional[Telemetry] = None,
        odds_policy: Optional[str] = None,
    ) -> None:
        self.spec = spec
        # Default to a disabled telemetry that performs no I/O.
        # Passing csv_path=None guarantees disabled mode (see Telemetry).
        self.telemetry = telemetry or Telemetry(csv_path=None)
        self.vs = VarStore.from_spec(spec)
        # odds_policy can be carried in table section; allow override
        self.odds_policy = odds_policy or spec.get("table", {}).get("odds_policy")

        # capture whether we’re on a comeout cycle from outside, if provided
        # (engine adapter will set vs.system fields as it learns table state)
        # nothing to do here yet.

        # Pre-resolved previous snapshot for event derivation
        self._prev_snapshot: Optional[Dict[str, Any]] = None

    def _snapshot_from_table(self, table: Any) -> Dict[str, Any]:
        """
        Convert a table-like object into a normalized snapshot dict the event
        layer understands. We keep this minimal; tests exercise only a few keys.
        """
        snap: Dict[str, Any] = {}

        # Heuristics for our test fakes (EngineAdapter tests pass _FakeTable and GameState)
        # Prefer attribute access, fallback to dict.
        def _get(obj, *attrs, default=None):
            cur = obj
            for a in attrs:
                if cur is None:
                    return default
                if isinstance(cur, dict):
                    cur = cur.get(a)
                else:
                    cur = getattr(cur, a, None)
            return cur if cur is not None else default

        # If table already looks like a GameState-ish object, surface those fields.
        # comeout flag
        comeout = _get(table, "comeout")
        if comeout is None:
            comeout = _get(table, "table", "comeout", default=False)
        snap["comeout"] = bool(comeout)

        # dice total if present
        total = _get(table, "total")
        if total is None:
            d = _get(table, "table", "dice")
            if isinstance(d, (tuple, list)) and len(d) >= 3:
                total = d[2]
        snap["total"] = total

        # point info
        snap["point_on"] = bool(_get(table, "point_on", default=_get(table, "table", "point_on", default=False)))
        snap["point_number"] = _get(table, "point_number", default=_get(table, "table", "point_number"))

        # signals possibly present on our GameState
        snap["just_established_point"] = bool(_get(table, "just_established_point", default=False))
        snap["just_made_point"] = bool(_get(table, "just_made_point", default=False))
        snap["just_seven_out"] = bool(_get(table, "just_seven_out", default=False))

        return snap

    def update_bets(self, table: Any) -> None:
        """
        Called by the engine adapter each roll. We:
          1) Take a light snapshot from the table
          2) Derive a high-level event
          3) Run rules to get intents
          4) Render/apply intents (materialize bets)
        """
        curr_snapshot = self._snapshot_from_table(table)
        prev_snapshot = self._prev_snapshot
        event = derive_event(prev_snapshot, curr_snapshot)

        # Run rules engine
        intents = run_rules_for_event(self.spec, self.vs, event)

        # Render a mode template if asked by rules (e.g., apply_template('Main'))
        rendered = render_template(self.spec, self.vs, intents)

        # Materialize to the table/player objects
        apply_intents(rendered, table, odds_policy=self.odds_policy)

        # Telemetry hook -- ignore if disabled
        self.telemetry.record_tick(event=event, intents=rendered, vs=self.vs)

        # Stash snapshot for next roll
        self._prev_snapshot = curr_snapshot