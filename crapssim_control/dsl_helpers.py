from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

from .dsl_parser import compile_rules, parse_file

rule_templates: Dict[str, str] = {
    "press_on_hit": "WHEN bets.{num} > 0 AND last_hit == {num} THEN press(number={num})",
    "regress_on_drawdown": "WHEN drawdown > {limit} THEN regress()",
    "lay_pull_on_point": "WHEN point_on AND lays.{num} > 0 AND point_value == {num} THEN take_down(number={num})",
    "odds_on_point": "WHEN point_on AND odds.{num} == 0 AND point_value == {num} THEN set_odds(number={num}, multiple=1)",
}


def generate_rule(template_name: str, **kwargs: Any) -> str:
    """Render a DSL rule from a template, substituting placeholders."""
    if template_name not in rule_templates:
        raise KeyError(
            f"Unknown template '{template_name}'. Available: {', '.join(rule_templates.keys())}"
        )
    template = rule_templates[template_name]
    try:
        text = template.format(**kwargs)
    except KeyError as exc:  # pragma: no cover - input contract validation
        raise ValueError(f"Missing placeholder: {exc}") from exc
    # Validate syntax via parser
    try:
        parse_file(text)
    except Exception as exc:  # pragma: no cover - propagate parse errors
        raise ValueError(f"Generated rule failed validation: {exc}") from exc
    return text


def validate_ruleset(path_or_text: str) -> Dict[str, Any]:
    """Parse and validate a DSL ruleset from a file or raw text."""
    if Path(path_or_text).exists():
        text = Path(path_or_text).read_text(encoding="utf-8")
        src = str(Path(path_or_text))
    else:
        text = path_or_text
        src = "<inline>"

    results: Dict[str, Any] = {"source": src, "valid": False, "count": 0, "errors": []}
    try:
        rules = parse_file(text)
        _ = compile_rules(rules)
        results["valid"] = True
        results["count"] = len(rules)
    except Exception as exc:  # pragma: no cover - parser/compiler failure surfaces in result
        results["errors"].append(str(exc))
    return results


def list_templates() -> List[str]:
    return list(rule_templates.keys())


# CLI entry (used by `csc dsl new` / `csc dsl validate`)
def cli_entry(argv: List[str]) -> int:
    if len(argv) < 2 or argv[1] not in {"new", "validate", "list"}:
        print("Usage: csc dsl [new|validate|list] ...")
        return 1

    cmd = argv[1]
    if cmd == "list":
        for name in list_templates():
            print(f"- {name}")
        return 0

    if cmd == "new":
        if len(argv) < 3:
            print("Usage: csc dsl new <template> [key=value ...]")
            return 1
        tpl = argv[2]
        kwargs: Dict[str, str] = {}
        for kv in argv[3:]:
            if "=" in kv:
                key, value = kv.split("=", 1)
                kwargs[key] = value
        try:
            print(generate_rule(tpl, **kwargs))
            return 0
        except Exception as exc:
            print(f"Error: {exc}")
            return 1

    if cmd == "validate":
        if len(argv) < 3:
            print("Usage: csc dsl validate <file_or_text>")
            return 1
        path = argv[2]
        res = validate_ruleset(path)
        if res["valid"]:
            print(f"Validated {res['count']} rule(s) from {res['source']}")
            return 0
        print("Errors:", *res["errors"], sep="\n  - ")
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli_entry(sys.argv))
