from __future__ import annotations
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass
class DecisionAttempt:
    roll_index: int
    window: str
    rule_id: str
    origin: str
    when_expr: str
    evaluated_true: bool
    verb: str
    args: Dict[str, Any]
    legal: bool
    applied: bool
    reason: Optional[str] = None


DecisionResult = DecisionAttempt  # alias
DecisionSnapshot = Dict[str, Any]


class DecisionsJournal:
    def __init__(self, artifacts_dir: str, verbose: bool = False):
        self.path = Path(artifacts_dir) / "decisions.jsonl"
        self.verbose = verbose
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, attempt: DecisionAttempt) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(attempt), separators=(",", ":")) + "\n")
