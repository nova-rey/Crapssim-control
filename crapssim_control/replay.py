"""Replay utilities for deterministic command tapes."""

from __future__ import annotations

from typing import Any, Dict, Optional

from crapssim_control.external.command_tape import iter_commands


class ReplayRunner:
    def __init__(self, controller: Any, tape: Dict[str, Any], seed: Optional[int] = None):
        self.controller = controller
        self.tape = tape
        self.seed = seed

    def run(self) -> Dict[str, Any]:
        adapter = getattr(self.controller, "adapter", None)
        if self.seed is not None and adapter and hasattr(adapter, "set_seed"):
            adapter.set_seed(self.seed)
        for verb, args in iter_commands(self.tape):
            if not verb:
                continue
            if adapter and hasattr(adapter, "apply_action"):
                adapter.apply_action(str(verb), args)
        if adapter and hasattr(adapter, "snapshot_state"):
            return adapter.snapshot_state()
        return {}
