import warnings

_issued = set()


def warn_once(key: str, message: str) -> None:
    """Emit a ``DeprecationWarning`` once per unique key."""
    if key not in _issued:
        warnings.warn(message, DeprecationWarning, stacklevel=2)
        _issued.add(key)
