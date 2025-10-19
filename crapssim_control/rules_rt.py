from .deprecations import warn_once
from .rules_engine import *  # noqa: F403,F401

warn_once("rules_rt", "Deprecated: import from canonical module instead of *_rt.")
