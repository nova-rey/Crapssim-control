import warnings
warnings.warn(
    "Deprecated: import from templates, rules_engine, or legalize instead of *_rt.",
    DeprecationWarning,
    stacklevel=2,
)
from .legalize import *  # noqa: F403,F401
