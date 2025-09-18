# crapssim_control/spec_schema.py
"""
Batch 17 -- Spec Schema (lenient)

This module exposes a *Python dict* describing the expected shape of a
control SPEC. It's intentionally permissive to avoid breaking existing
specs. The stricter, actionable checks live in `spec_validate.py`.
"""

SPEC_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": True,
    "required": ["table", "variables", "modes", "rules"],
    "properties": {
        "meta": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "name": {"type": ["string", "null"]},
                "version": {"type": ["integer", "number", "string", "null"]},
                "description": {"type": ["string", "null"]},
            },
        },
        "table": {
            "type": "object",
            "additionalProperties": True,
            "required": ["bubble", "level"],
            "properties": {
                "bubble": {"type": "boolean"},
                "level": {"type": ["integer", "number"]},
                "odds_policy": {"type": ["string", "null"]},
            },
        },
        "variables": {
            "type": "object",
            "additionalProperties": True,
            # Don't require 'units' here; tests sometimes set it via rules.
        },
        "modes": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    # Template values can be:
                    #  - number       (e.g., 10)
                    #  - string expr  (e.g., "units")
                    #  - object {"amount": <number|string expr>}
                    "template": {
                        "type": ["object", "null"],
                        "additionalProperties": {
                            "oneOf": [
                                {"type": ["number", "integer", "string"]},
                                {
                                    "type": "object",
                                    "additionalProperties": True,
                                    "properties": {
                                        "amount": {
                                            "type": ["number", "integer", "string"]
                                        }
                                    },
                                },
                            ]
                        },
                    },
                },
            },
        },
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": True,
                "required": ["on", "do"],
                "properties": {
                    "on": {
                        "type": "object",
                        "additionalProperties": True,
                        "properties": {
                            "event": {"type": ["string", "null"]},
                            "bet": {"type": ["string", "null"]},
                            "result": {"type": ["string", "null"]},
                            # Allow other filters, but don't enumerate.
                        },
                    },
                    "do": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
    },
}