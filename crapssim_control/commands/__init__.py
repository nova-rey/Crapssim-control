"""Command entrypoints for CLI wiring."""

from .init_cmd import run as init_run  # noqa: F401
from .doctor_cmd import run as doctor_run  # noqa: F401
from .summarize_cmd import run as summarize_run  # noqa: F401

__all__ = [
    "init_run",
    "doctor_run",
    "summarize_run",
]
