"""Pytest configuration for Crapssim Control."""

from __future__ import annotations

import sys
import warnings
from pathlib import Path


def _ensure_repo_on_path() -> None:
    """Make the repository importable without an editable install."""
    repo_root = Path(__file__).resolve().parent.parent
    if repo_root.exists():
        path_str = str(repo_root)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


_ensure_repo_on_path()
warnings.simplefilter("default", DeprecationWarning)
