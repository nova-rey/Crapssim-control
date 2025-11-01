from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(slots=True)
class ControllerRunResult:
    """Lightweight summary of controller outputs for CLI consumption."""

    summary: Optional[dict[str, Any]] = None
    journal_path: Optional[Path] = None


__all__ = ["ControllerRunResult"]
