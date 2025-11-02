"""CSC HTTP API surface for the lightweight FastAPI shim."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from .spec_loader import normalize_deprecated_keys

logger = logging.getLogger("CSC.http_api")


# ---------------------------------------------------------------------------
# Environment-driven configuration
# ---------------------------------------------------------------------------


def _refresh_config_from_env() -> None:
    """Load mutable configuration derived from environment variables."""

    artifacts_dir = Path(os.getenv("CSC_ARTIFACTS_DIR", "artifacts")).resolve()
    ui_static_dir = Path(os.getenv("CSC_UI_STATIC_DIR", "ui_static")).resolve()
    token = os.getenv("CSC_API_TOKEN", "").strip() or None
    cors_raw = os.getenv("CSC_CORS_ORIGINS", "")
    origins = [origin.strip() for origin in cors_raw.split(",") if origin.strip()]

    globals().update(
        {
            "ARTIFACTS_ROOT": artifacts_dir,
            "UI_STATIC_DIR": ui_static_dir,
            "API_TOKEN": token,
            "CORS_ORIGINS": origins,
        }
    )


ARTIFACTS_ROOT: Path
UI_STATIC_DIR: Path
API_TOKEN: Optional[str]
CORS_ORIGINS: List[str]
_refresh_config_from_env()


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------


def error_response(
    code: str,
    message: str,
    *,
    status: int = 400,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """Return a JSON error envelope used across the API."""

    payload: Dict[str, Any] = {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }
    return JSONResponse(status_code=status, content=payload)


def ok_response(payload: Dict[str, Any], *, status: int = 200) -> JSONResponse:
    """Return a JSON success envelope."""

    data = {"ok": True}
    data.update(payload)
    return JSONResponse(status_code=status, content=data)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def require_bearer(
    request: Optional[Request] = None,
    *,
    authorization: Optional[str] = None,
) -> Optional[JSONResponse]:
    """Optional bearer token guard using ``CSC_API_TOKEN``."""

    if API_TOKEN is None:
        return None

    header_value = authorization
    if header_value is None and request is not None:
        header_value = request.headers.get("Authorization")

    if not header_value or not header_value.lower().startswith("bearer "):
        return error_response("AUTH_REQUIRED", "Missing bearer token", status=401)

    token = header_value.split(" ", 1)[1].strip()
    if token != API_TOKEN:
        return error_response("AUTH_INVALID", "Invalid bearer token", status=401)

    return None


# ---------------------------------------------------------------------------
# Run helpers
# ---------------------------------------------------------------------------


def _list_runs_sorted(root: Optional[Path] = None) -> List[Path]:
    """Return run directories ordered by most recent modification time."""

    base = root or ARTIFACTS_ROOT
    if not base.exists():
        return []

    runs = [path for path in base.iterdir() if path.is_dir()]
    runs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return runs


def _run_status(run_dir: Path) -> Dict[str, Any]:
    """Collect status metadata for a single run directory."""

    summary = run_dir / "summary.json"
    manifest = run_dir / "manifest.json"
    journal = run_dir / "journal.csv"
    decisions = run_dir / "decisions.csv"

    state = "finished" if summary.exists() and manifest.exists() else "unknown"

    return {
        "id": run_dir.name,
        "state": state,
        "has": {
            "summary": summary.exists(),
            "manifest": manifest.exists(),
            "journal": journal.exists(),
            "decisions": decisions.exists(),
        },
        "paths": {
            "summary": str(summary) if summary.exists() else None,
            "manifest": str(manifest) if manifest.exists() else None,
            "journal": str(journal) if journal.exists() else None,
            "decisions": str(decisions) if decisions.exists() else None,
        },
        "mtime": run_dir.stat().st_mtime,
    }


def _sample_journal_lines(journal_path: Path, max_events: int) -> List[Dict[str, Any]]:
    """Sample up to ``max_events`` lines from the journal CSV."""

    if not journal_path.exists():
        return []

    capped = max(1, min(max_events, 10_000))
    results: List[Dict[str, Any]] = []
    header: Optional[List[str]] = None

    with journal_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if header is None:
                header = [column.strip() for column in stripped.split(",")]
                continue

            cells = [cell.strip() for cell in stripped.split(",")]
            row = {
                header[index]: cells[index] if index < len(cells) else ""
                for index in range(len(header))
            }
            results.append(row)
            if len(results) >= capped:
                break

    return results


# ---------------------------------------------------------------------------
# Spec helpers
# ---------------------------------------------------------------------------


def _normalize_spec_payload(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Apply basic spec normalization routines."""

    clone = dict(spec)
    normalized, _ = normalize_deprecated_keys(clone)
    return normalized


def _spec_to_graph_payload(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Produce a lightweight graph-friendly view of a spec."""

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, str]] = []

    table = spec.get("table")
    if isinstance(table, dict):
        nodes.append({"id": "table", "type": "table", "attributes": table})

    rules = spec.get("rules")
    if isinstance(rules, list):
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict):
                continue
            node_id = f"rule-{index}"
            nodes.append({"id": node_id, "type": "rule", "attributes": rule})
            edges.append({"from": "table", "to": node_id, "kind": "applies_to"})

    return {
        "version": "csc.graph.v1",
        "nodes": nodes,
        "edges": edges,
    }


def _payload_from_request(request: Optional[Request]) -> Dict[str, Any]:
    if request is None:
        return {}
    payload = getattr(request, "payload", {})
    if isinstance(payload, dict):
        return payload
    return {}


# ---------------------------------------------------------------------------
# Routers & endpoints
# ---------------------------------------------------------------------------

api_v1_router = APIRouter()
api_router = api_v1_router


@api_v1_router.post("/v1/spec/normalize")
def api_spec_normalize(request: Request):
    auth_error = require_bearer(request)
    if auth_error:
        return auth_error

    payload = _payload_from_request(request)
    spec = payload.get("spec") or {}
    if not isinstance(spec, dict):
        return error_response("INVALID_SPEC", "Spec payload must be an object", status=422)

    normalized = _normalize_spec_payload(spec)
    return ok_response({"spec": normalized})


@api_v1_router.post("/v1/spec/to_graph")
def api_spec_to_graph(request: Request):
    auth_error = require_bearer(request)
    if auth_error:
        return auth_error

    payload = _payload_from_request(request)
    spec = payload.get("spec") or {}
    if not isinstance(spec, dict):
        return error_response("INVALID_SPEC", "Spec payload must be an object", status=422)

    graph = _spec_to_graph_payload(spec)
    return ok_response({"graph": graph})


@api_v1_router.get("/v1/runs")
def api_runs_list(request: Request):
    auth_error = require_bearer(request)
    if auth_error:
        return auth_error

    params = getattr(request, "query_params", {}) or {}
    limit_raw = params.get("limit", "25")
    cursor = params.get("cursor")

    try:
        limit_value = int(limit_raw)
    except (TypeError, ValueError):
        limit_value = 25

    limit_value = max(1, min(limit_value, 100))

    runs = _list_runs_sorted()

    start_index = 0
    if cursor:
        for index, path in enumerate(runs):
            if path.name == cursor:
                start_index = index + 1
                break

    window = runs[start_index : start_index + limit_value]
    items = [_run_status(path) for path in window]
    has_more = start_index + limit_value < len(runs)
    next_cursor = window[-1].name if window and has_more else None

    return ok_response({"items": items, "next_cursor": next_cursor})


@api_v1_router.get("/v1/runs/{run_id}")
def api_runs_get(run_id: str, request: Request):
    auth_error = require_bearer(request)
    if auth_error:
        return auth_error

    run_dir = ARTIFACTS_ROOT / run_id
    if not run_dir.exists() or not run_dir.is_dir():
        return error_response("NOT_FOUND", f"Run {run_id} not found", status=404)

    return ok_response({"data": _run_status(run_dir)})


@api_v1_router.get("/v1/runs/{run_id}/replay")
def api_runs_replay(run_id: str, request: Request):
    auth_error = require_bearer(request)
    if auth_error:
        return auth_error

    params = getattr(request, "query_params", {}) or {}
    rate = params.get("rate", "5hz")
    max_events_raw = params.get("max_events", "200")

    try:
        max_events = int(max_events_raw)
    except (TypeError, ValueError):
        max_events = 200

    max_events = max(1, min(max_events, 10_000))

    run_dir = ARTIFACTS_ROOT / run_id
    if not run_dir.exists() or not run_dir.is_dir():
        return error_response("NOT_FOUND", f"Run {run_id} not found", status=404)

    journal = run_dir / "journal.csv"
    events = _sample_journal_lines(journal, max_events=max_events)
    return ok_response({"rate": rate, "events": events})


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Create a FastAPI application configured for CSC control."""

    _refresh_config_from_env()

    app = FastAPI(title="CSC API", version="1.0.0")
    app.state.CSC_ARTIFACTS_DIR = str(ARTIFACTS_ROOT)
    app.state.CSC_UI_STATIC_DIR = str(UI_STATIC_DIR)
    app.state.CSC_API_TOKEN = API_TOKEN
    app.state.CSC_CORS_ORIGINS = list(CORS_ORIGINS)

    app.include_router(api_v1_router, prefix="/api")

    @app.get("/api")
    def legacy_root():
        return ok_response({"notice": "Unversioned /api is deprecated; use /api/v1"})

    @app.get("/api/_deprecated")
    def legacy_deprecated():
        return ok_response({"notice": "Unversioned /api is deprecated; use /api/v1"})

    if UI_STATIC_DIR.exists() and UI_STATIC_DIR.is_dir():
        index_path = UI_STATIC_DIR / "index.html"

        @app.get("/ui/")
        def ui_root():
            if index_path.exists():
                try:
                    return index_path.read_text(encoding="utf-8")
                except Exception:  # pragma: no cover - defensive
                    logger.exception("Failed to read UI index from %s", index_path)
                    return error_response("UI_READ_FAILED", "Failed to load UI index", status=500)
            return error_response("NOT_FOUND", "UI index not found", status=404)

    @app.get("/health")
    def health():
        return ok_response({"status": "ok", "time": time.time()})

    return app


app = create_app()

__all__ = [
    "ARTIFACTS_ROOT",
    "API_TOKEN",
    "CORS_ORIGINS",
    "UI_STATIC_DIR",
    "api_router",
    "api_v1_router",
    "app",
    "create_app",
    "error_response",
    "ok_response",
    "require_bearer",
]
