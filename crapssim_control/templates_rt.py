from .deprecations import warn_once
from .templates import *  # noqa: F403,F401

warn_once("templates_rt", "Deprecated: import from canonical module instead of *_rt.")
