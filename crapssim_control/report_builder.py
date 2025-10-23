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


def apply_policy_summary_fields(summary: Dict[str, Any], adapter: Any) -> None:
    """Populate policy counters on the summary payload."""

    summary["risk_violations_count"] = int(
        getattr(adapter, "_policy_violations", 0) if adapter is not None else 0
    )
    summary["policy_applied_count"] = int(
        getattr(adapter, "_policy_applied", 0) if adapter is not None else 0
    )


def apply_policy_manifest_fields(manifest: Dict[str, Any], adapter: Any) -> None:
    """Annotate manifest with the adapter's risk policy version."""

    risk_policy = getattr(adapter, "_risk_policy", None)
    manifest["risk_policy_version"] = getattr(risk_policy, "version", "1.0")
