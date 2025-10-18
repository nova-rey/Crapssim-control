"""Centralized CLI flag definitions and defaults for CrapsSim-Control."""
from dataclasses import dataclass


@dataclass
class CLIFlags:
    strict: bool = False
    strict_source: str = "default"
    demo_fallbacks: bool = False
    demo_fallbacks_source: str = "default"
    embed_analytics: bool = True
    embed_analytics_source: str = "default"
    export: bool = False
    export_source: str = "default"
    webhook_url: str | None = None
    webhook_url_source: str = "default"
    webhook_timeout: float = 2.0
    webhook_enabled: bool = False
    webhook_enabled_source: str = "default"
    evo_enabled: bool = False
    trial_tag: str | None = None


def parse_flags(args):
    flags = CLIFlags()

    if "--strict" in args:
        flags.strict = True
        flags.strict_source = "cli"

    if "--demo-fallbacks" in args:
        flags.demo_fallbacks = True
        flags.demo_fallbacks_source = "cli"

    if "--no-embed-analytics" in args:
        flags.embed_analytics = False
        flags.embed_analytics_source = "cli"

    if "--export" in args:
        flags.export = True
        flags.export_source = "cli"

    if "--webhook-url" in args:
        try:
            idx = args.index("--webhook-url")
            flags.webhook_url = args[idx + 1]
        except (ValueError, IndexError):
            flags.webhook_url = None
        flags.webhook_enabled = True
        flags.webhook_url_source = "cli"
        flags.webhook_enabled_source = "cli"

    if "--webhook-timeout" in args:
        try:
            idx = args.index("--webhook-timeout")
            flags.webhook_timeout = float(args[idx + 1])
        except (ValueError, IndexError, TypeError):
            flags.webhook_timeout = 2.0

    if "--no-webhook" in args:
        flags.webhook_enabled = False
        flags.webhook_enabled_source = "cli"

    if "--evo-enabled" in args:
        flags.evo_enabled = True

    if "--trial-tag" in args:
        i = args.index("--trial-tag")
        if i + 1 < len(args):
            flags.trial_tag = args[i + 1]

    # Ensure defaults retain explicit provenance markers.
    flags.strict_source = flags.strict_source or "default"
    flags.demo_fallbacks_source = flags.demo_fallbacks_source or "default"
    flags.embed_analytics_source = flags.embed_analytics_source or "default"
    flags.export_source = flags.export_source or "default"
    flags.webhook_enabled_source = flags.webhook_enabled_source or "default"
    if flags.webhook_url:
        flags.webhook_url_source = flags.webhook_url_source or "cli"
    else:
        flags.webhook_url_source = "default"

    return flags
