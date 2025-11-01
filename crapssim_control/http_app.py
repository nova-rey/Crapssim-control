from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI


def create_app(*, mount_ui: bool = True) -> FastAPI:
    """Factory for the CSC FastAPI application."""

    try:
        app = FastAPI(title="CSC", version="0.1")
    except TypeError:  # pragma: no cover - legacy lightweight FastAPI shim
        app = FastAPI()
        setattr(app, "title", "CSC")
        setattr(app, "version", "0.1")

    # Attempt to mount existing API routers if present. Import lazily so this
    # factory can be used without the optional API module being installed.
    try:  # pragma: no cover - optional import
        from crapssim_control.http_api import api_router  # type: ignore

        app.include_router(api_router, prefix="/api")
    except Exception:  # pragma: no cover - router is optional
        pass

    if mount_ui:
        from crapssim_control.ui.router import ui_router

        app.include_router(ui_router, prefix="/ui", tags=["ui"])

        @app.get("/", include_in_schema=False)
        def _root():  # pragma: no cover - simple redirect
            from fastapi.responses import RedirectResponse

            return RedirectResponse(url="/ui")

        static_dir = Path(__file__).parent / "ui" / "static"
        try:
            from fastapi.staticfiles import StaticFiles  # type: ignore
        except Exception:  # pragma: no cover - optional static support
            StaticFiles = None  # type: ignore

        if StaticFiles is not None:
            app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    return app
