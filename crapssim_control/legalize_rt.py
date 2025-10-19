from .deprecations import warn_once
from .legalize import *  # noqa: F403,F401

warn_once("legalize_rt", "Deprecated: import from canonical module instead of *_rt.")
