import logging
import sys

def setup_logging(verbosity: int = 0) -> None:
    """
    verbosity: 0=WARNING, 1=INFO, 2+=DEBUG
    """
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG

    root = logging.getLogger()
    # If already configured, don't double-add handlers
    if root.handlers:
        root.setLevel(level)
        return

    handler = logging.StreamHandler(stream=sys.stdout)
    fmt = "[%(levelname)s] %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    root.addHandler(handler)
    root.setLevel(level)