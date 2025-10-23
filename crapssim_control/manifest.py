"""Run Manifest generator and capability embedding helpers."""

from uuid import uuid4
from datetime import datetime
from typing import Any, Dict, Mapping, Optional

from .capabilities import get_capabilities
from .schemas import JOURNAL_SCHEMA_VERSION, SUMMARY_SCHEMA_VERSION


def iso_now():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def generate_manifest(
    spec_file: str,
    cli_flags: dict,
    outputs: dict,
    *,
    engine_version: str = None,
    run_id: str | None = None,
):
    manifest_run_id = str(run_id) if run_id else str(uuid4())
    return {
        "run_id": manifest_run_id,
        "timestamp": iso_now(),
        "spec_file": spec_file,
        "cli_flags": cli_flags,
        "schema": {
            "journal": JOURNAL_SCHEMA_VERSION,
            "summary": SUMMARY_SCHEMA_VERSION
        },
        "engine_version": engine_version,
        "output_paths": outputs,
        "integrations": {
            "webhook": {
                "enabled": bool(cli_flags.get("webhook_enabled", False)),
                "url_present": bool(cli_flags.get("webhook_url")),
                "timeout": float(cli_flags.get("webhook_timeout", 2.0)),
            }
        },
        "evo": {
            "enabled": bool(cli_flags.get("evo_enabled", False)),
            "trial_tag": cli_flags.get("trial_tag"),
        },
        "ui": {"report_url": None, "journal_url": None},
    }


def _resolve_capabilities(adapter: Any | None) -> Dict[str, Any]:
    if adapter is not None:
        get_caps = getattr(adapter, "get_capabilities", None)
        if callable(get_caps):
            try:
                caps = get_caps()
                if isinstance(caps, Mapping):
                    return dict(caps)
            except Exception:
                pass
    raw_caps = get_capabilities()
    return dict(raw_caps) if isinstance(raw_caps, Mapping) else {}


def _build_manifest_base(
    run_id: str, report: Mapping[str, Any] | None, adapter: Optional[Any] = None
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "run_id": run_id,
        "report": dict(report) if isinstance(report, Mapping) else {},
    }
    payload["capabilities"] = _resolve_capabilities(adapter)
    payload.setdefault("capabilities_schema_version", "1.1")
    engine_info = getattr(adapter, "get_engine_info", lambda: {})()
    payload["engine_info"] = engine_info
    risk_policy = getattr(adapter, "_risk_policy", None)
    payload["risk_policy_version"] = getattr(risk_policy, "version", "1.0")
    if hasattr(adapter, "transport") and isinstance(getattr(adapter, "transport"), object):
        transport = getattr(adapter, "transport")
        base_url = getattr(transport, "base_url", "")
        if hasattr(transport, "base_url") and "http" in base_url:
            payload["engine_mode"] = "remote"
            payload["remote_base_url"] = base_url
    return payload


def build_manifest(
    run_id: str, report: Mapping[str, Any] | None, adapter: Optional[Any] = None
) -> Dict[str, Any]:
    """Build a manifest payload that includes capability and perf metadata."""

    base = _build_manifest_base(run_id, report, adapter=adapter)
    base["error_surface_schema_version"] = "1.0"
    base["replay_schema_version"] = "1.0"
    try:
        from crapssim_control.replay_tester import run_perf_test

        perf = run_perf_test(rolls=1000)
        base["perf_metrics"] = {"rps": perf["rps"], "elapsed": perf["elapsed"]}
    except Exception:
        base["perf_metrics"] = {"rps": 0, "elapsed": 0}
    return base
