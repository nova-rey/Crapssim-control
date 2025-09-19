from __future__ import annotations

import logging
import sys
from typing import Optional


_LEVELS_BY_VERBOSE = {
    0: logging.WARNING,  # default
    1: logging.INFO,
    2: logging.DEBUG,    # 2 or more → DEBUG
}


def setup_logging(verbose_count: int = 0, logger_name: Optional[str] = None) -> logging.Logger:
    """
    Configure root (or named) logger based on -v count.

    -v  → INFO
    -vv → DEBUG
    default → WARNING

    Idempotent: won't add duplicate handlers if called again.
    """
    level = _LEVELS_BY_VERBOSE.get(verbose_count, logging.DEBUG)
    name = logger_name or ""  # empty string means root logger
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Check if we already attached our handler (by a custom attribute)
    already_configured = any(getattr(h, "_crapssim_ctl_handler", False) for h in logger.handlers)
    if not already_configured:
        handler = logging.StreamHandler(stream=sys.stderr)
        handler._crapssim_ctl_handler = True  # type: ignore[attr-defined]
        fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        handler.setFormatter(logging.Formatter(fmt=fmt, datefmt="%H:%M:%S"))
        logger.addHandler(handler)

    # Keep noisy third-party libs calm unless explicitly DEBUG
    if level > logging.DEBUG:
        for noisy in ("urllib3", "matplotlib", "asyncio"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    return logger