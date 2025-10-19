"""Replay utilities for deterministic command tapes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class ReplayRunner:
    def __init__(self, controller: Any, tape: List[Dict[str, Any]], seed: Optional[int] = None):
        self.controller = controller
        self.tape = tape
        self.seed = seed

    def run(self) -> Dict[str, Any]:
        adapter = getattr(self.controller, "adapter", None)
        if self.seed is not None and adapter and hasattr(adapter, "set_seed"):
            adapter.set_seed(self.seed)
        for cmd in self.tape:
            verb = cmd.get("verb")
            if not verb:
                continue
            args = cmd.get("args", {})
            if adapter and hasattr(adapter, "apply_action"):
                adapter.apply_action(str(verb), args)
        if adapter and hasattr(adapter, "snapshot_state"):
            return adapter.snapshot_state()
        return {}
