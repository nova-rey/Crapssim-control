"""Simple Jinja2 templating support for the FastAPI shim."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

try:  # pragma: no cover - optional dependency
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ModuleNotFoundError:  # pragma: no cover - fallback to raw templates
    Environment = None  # type: ignore[assignment]

from .responses import HTMLResponse

__all__ = ["Jinja2Templates"]


class Jinja2Templates:
    def __init__(self, directory: str) -> None:
        self.directory = Path(directory)
        if Environment is not None:
            self._env = Environment(
                loader=FileSystemLoader(str(self.directory)),
                autoescape=select_autoescape(["html", "xml"]),
            )
        else:
            self._env = None

    def TemplateResponse(self, name: str, context: Dict[str, Any]) -> HTMLResponse:
        if self._env is None:
            template_path = self.directory / name
            rendered = template_path.read_text(encoding="utf-8")
        else:
            template = self._env.get_template(name)
            rendered = template.render(**context)
        return HTMLResponse(rendered)
