"""Command tape recorder for external command auditing and replay."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Iterator


class CommandTape:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)

    def append(
        self,
        run_id: str,
        source: str,
        action: str,
        args: Optional[Dict[str, Any]],
        executed: bool,
        *,
        correlation_id: Optional[str] = None,
        rejection_reason: Optional[str] = None,
        hand_id: Optional[int] = None,
        roll_in_hand: Optional[int] = None,
        seq: Optional[int] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "ts": time.time(),
            "run_id": run_id,
            "source": source,
            "action": action,
            "args": dict(args or {}),
            "executed": bool(executed),
        }
        if correlation_id is not None:
            payload["correlation_id"] = correlation_id
        if rejection_reason is not None:
            payload["rejection_reason"] = rejection_reason
        if hand_id is not None:
            payload["hand_id"] = hand_id
        if roll_in_hand is not None:
            payload["roll_in_hand"] = roll_in_hand
        if seq is not None:
            payload["journal_seq"] = seq

        dest = Path(self.path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")


TAPE_SCHEMA_VERSION = "1.0"
_ALLOWED_CMD_KEYS = {"verb", "args"}


def record_command_tape(commands: list[dict]) -> dict:
    """Wrap a list of verb/args dicts with schema metadata."""

    for cmd in commands:
        extra = set(cmd.keys()) - _ALLOWED_CMD_KEYS
        if extra:
            raise ValueError(f"tape_cmd_extra_keys:{sorted(extra)}")
        if "verb" not in cmd:
            raise ValueError("tape_cmd_missing:verb")
        if "args" in cmd and not isinstance(cmd["args"], dict):
            raise ValueError("tape_cmd_invalid:args_type")

    return {
        "tape_schema": TAPE_SCHEMA_VERSION,
        "commands": list(commands),
    }


def iter_commands(tape: dict) -> Iterator[tuple[str, Dict[str, Any]]]:
    """Yield normalized verb/args pairs from a recorded command tape."""

    schema = tape.get("tape_schema")
    if schema != TAPE_SCHEMA_VERSION:
        raise ValueError(f"tape_schema_mismatch:{schema}")
    for cmd in tape.get("commands", []):
        verb = cmd["verb"]
        args = cmd.get("args") or {}
        if not isinstance(args, dict):
            raise ValueError("tape_cmd_invalid:args_type")
        yield verb, args
