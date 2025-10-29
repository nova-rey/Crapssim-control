from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any

from .schemas import JOB_SCHEMA_VERSION, DONE_SCHEMA_VERSION, ERROR_SCHEMA_VERSION


@dataclass
class EvoJob:
    schema_version: str
    request_id: str
    bundle_id: str
    bundle_path: str
    generation: str
    seed: int
    run_flags: Dict[str, Any]
    max_rolls: Optional[int] = None
    webhook_url: Optional[str] = None


@dataclass
class DoneReceipt:
    schema_version: str = DONE_SCHEMA_VERSION
    request_id: str = ""
    bundle_id: str = ""
    generation: str = ""
    run_id: str = ""
    results_root: str = ""
    summary: Dict[str, Any] | None = None
    status: str = "ok"


@dataclass
class ErrorReceipt:
    schema_version: str = ERROR_SCHEMA_VERSION
    request_id: str = ""
    bundle_id: str = ""
    generation: str = ""
    run_id: str = ""
    status: str = "error"
    error_code: str = ""
    error_detail: str = ""
    partial_results_root: Optional[str] = None
