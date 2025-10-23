"""Report helpers for journaling and trace metadata."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

TRACE_SCHEMA_VERSION = "1.0"


def attach_trace_metadata(
    report: Dict[str, Any],
    *,
    trace_count: Optional[int] = None,
    journal_entries: Optional[Iterable[Dict[str, Any]]] = None,
) -> None:
    """Attach DSL trace summary metadata to the report."""

    report.setdefault("dsl_schema_version", "1.0")
    report.setdefault("trace_schema_version", TRACE_SCHEMA_VERSION)

    resolved_count = trace_count
    if resolved_count is None and journal_entries is not None:
        resolved_count = sum(
            1
            for entry in journal_entries
            if isinstance(entry, dict) and entry.get("type") == "dsl_trace"
        )
    if resolved_count is None:
        resolved_count = 0
    report["dsl_trace_count"] = int(resolved_count)
    report["trace_schema_version"] = TRACE_SCHEMA_VERSION


def attach_manifest_risk_overrides(
    manifest: Dict[str, Any],
    adapter: Optional[Any],
) -> None:
    """Attach policy override metadata to the manifest."""

    if not isinstance(manifest, dict):
        return
    overrides = {}
    if adapter is not None:
        overrides_obj = getattr(adapter, "_policy_overrides", {})
        if isinstance(overrides_obj, dict):
            overrides = dict(overrides_obj)
    manifest["risk_overrides"] = overrides


def attach_termination_metadata(
    summary: Optional[Dict[str, Any]],
    manifest: Optional[Dict[str, Any]],
    adapter: Optional[Any],
) -> None:
    """Attach early termination metadata to summary and manifest outputs."""

    if not isinstance(summary, dict):
        summary_dict: Dict[str, Any] = {}
    else:
        summary_dict = summary

    terminated = bool(getattr(adapter, "_terminated_early", False))
    reason = getattr(adapter, "_termination_reason", None)
    try:
        rolls_completed = int(getattr(adapter, "_rolls_completed", 0))
    except Exception:
        rolls_completed = 0
    try:
        rolls_requested = int(getattr(adapter, "_rolls_requested", 0))
    except Exception:
        rolls_requested = 0

    summary_dict["terminated_early"] = terminated
    summary_dict["termination_reason"] = reason
    summary_dict["rolls_completed"] = rolls_completed
    summary_dict["rolls_requested"] = rolls_requested

    if isinstance(manifest, dict):
        manifest["terminated_early"] = terminated
        manifest["termination_reason"] = reason
        manifest["rolls_completed"] = rolls_completed
        manifest["rolls_requested"] = rolls_requested

    if summary is not summary_dict and isinstance(summary, dict):
        summary.clear()
        summary.update(summary_dict)
