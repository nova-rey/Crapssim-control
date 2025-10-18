"""
Centralized CLI flag definitions and defaults for CrapsSim-Control.
"""
from dataclasses import dataclass


@dataclass
class CLIFlags:
    strict: bool = False
    demo_fallbacks: bool = False
    embed_analytics: bool = True
    export: bool = False


def parse_flags(args):
    flags = CLIFlags()
    if "--strict" in args:
        flags.strict = True
    if "--demo-fallbacks" in args:
        flags.demo_fallbacks = True
    if "--no-embed-analytics" in args:
        flags.embed_analytics = False
    if "--export" in args:
        flags.export = True
    return flags
