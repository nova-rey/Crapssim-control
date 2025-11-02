from __future__ import annotations

import html
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates


ui_router = APIRouter()
_templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _artifacts_root(req: Request) -> Path:
    """Resolve the artifacts directory for the current application."""

    root = Path(str(req.app.state.__dict__.get("CSC_ARTIFACTS_DIR", "")) or "./artifacts")
    root.mkdir(parents=True, exist_ok=True)
    return root


@ui_router.get("", response_class=HTMLResponse)
def home(request: Request):
    art = _artifacts_root(request)
    runs = sorted(
        [p for p in art.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    rows = []
    for run_dir in runs:
        rows.append(
            {
                "id": run_dir.name,
                "has_decisions": (run_dir / "decisions.csv").exists(),
                "has_summary": (run_dir / "summary.json").exists(),
                "has_manifest": (run_dir / "manifest.json").exists(),
                "has_report": (run_dir / "report.md").exists(),
            }
        )
    return _templates.TemplateResponse("home.html", {"request": request, "runs": rows})


@ui_router.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(request: Request, run_id: str):
    run_dir = _artifacts_root(request) / run_id
    ctx: dict[str, object] = {
        "request": request,
        "run_id": run_id,
        "exists": run_dir.exists(),
    }
    if run_dir.exists():
        ctx.update(
            {
                "has_decisions": (run_dir / "decisions.csv").exists(),
                "has_summary": (run_dir / "summary.json").exists(),
                "has_manifest": (run_dir / "manifest.json").exists(),
                "has_report": (run_dir / "report.md").exists(),
            }
        )
        report = run_dir / "report.md"
        if report.exists():
            try:
                ctx["report_html"] = (
                    "<pre>" + html.escape(report.read_text(encoding="utf-8")) + "</pre>"
                )
            except Exception:  # pragma: no cover - defensive fallback
                ctx["report_html"] = "<em>Could not read report.md</em>"
    return _templates.TemplateResponse("run_detail.html", ctx)


@ui_router.get("/download/{run_id}/{name}")
def download_artifact(request: Request, run_id: str, name: str):
    run_dir = _artifacts_root(request) / run_id
    target = run_dir / name
    if not target.exists():
        return PlainTextResponse("Not found", status_code=404)
    from fastapi.responses import FileResponse

    return FileResponse(str(target), filename=name)


@ui_router.post("/runs/{run_id}/summarize")
def run_summarize(request: Request, run_id: str):
    run_dir = _artifacts_root(request) / run_id
    if not run_dir.exists():
        return PlainTextResponse("Run not found", status_code=404)
    subprocess.run(  # noqa: S603,S607 - intentional CLI invocation
        [
            sys.executable,
            "-m",
            "csc",
            "summarize",
            "--artifacts",
            str(run_dir),
            "--human",
        ],
        text=True,
        capture_output=True,
    )
    return RedirectResponse(url=f"/ui/runs/{run_id}", status_code=303)


@ui_router.get("/doctor", response_class=HTMLResponse)
def doctor_form(request: Request):
    return _templates.TemplateResponse("doctor.html", {"request": request})


@ui_router.post("/doctor", response_class=HTMLResponse)
def doctor_submit(request: Request, spec_path: str = Form(...)):
    result = subprocess.run(  # noqa: S603,S607 - intentional CLI invocation
        [sys.executable, "-m", "csc", "doctor", "--spec", spec_path],
        text=True,
        capture_output=True,
    )
    return _templates.TemplateResponse(
        "doctor.html",
        {
            "request": request,
            "spec_path": spec_path,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        },
    )


@ui_router.get("/launch", response_class=HTMLResponse)
def launch_form(request: Request):
    return _templates.TemplateResponse("launch.html", {"request": request})


@ui_router.post("/launch")
def launch_submit(
    request: Request,
    spec_path: str = Form(...),
    seed: str = Form("4242"),
    explain: str = Form("on"),
):
    args = [sys.executable, "-m", "csc", "run", "--spec", spec_path, "--seed", seed]
    if explain == "on":
        args.append("--explain")
    subprocess.run(args, text=True, capture_output=True)  # noqa: S603,S607
    art = _artifacts_root(request)
    runs = [p for p in art.iterdir() if p.is_dir()]
    run_id = ""
    if runs:
        run_id = sorted(runs, key=lambda p: p.stat().st_mtime, reverse=True)[0].name
    target_url = f"/ui/runs/{run_id}" if run_id else "/ui"
    return RedirectResponse(url=target_url, status_code=303)
