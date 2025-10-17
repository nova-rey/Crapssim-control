from .deprecations import warn_once

warn_once("legalize_rt", "Deprecated: import from canonical module instead of *_rt.")
from .legalize import *  # noqa: F403,F401
