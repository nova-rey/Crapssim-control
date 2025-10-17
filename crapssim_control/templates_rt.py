from .deprecations import warn_once

warn_once("templates_rt", "Deprecated: import from canonical module instead of *_rt.")
from .templates import *  # noqa: F403,F401
