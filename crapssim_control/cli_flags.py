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
    webhook_url: str | None = None
    webhook_timeout: float = 2.0
    webhook_enabled: bool = False


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

    if "--webhook-url" in args:
        try:
            idx = args.index("--webhook-url")
            flags.webhook_url = args[idx + 1]
        except (ValueError, IndexError):
            flags.webhook_url = None
        flags.webhook_enabled = True
    if "--webhook-timeout" in args:
        try:
            idx = args.index("--webhook-timeout")
            flags.webhook_timeout = float(args[idx + 1])
        except (ValueError, IndexError, TypeError):
            flags.webhook_timeout = 2.0
    if "--no-webhook" in args:
        flags.webhook_enabled = False

    return flags
