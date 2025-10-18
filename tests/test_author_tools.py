import json

import yaml

from crapssim_control.rules_engine.author import RuleBuilder


def test_macro_expands_params(tmp_path):
    macro_path = tmp_path / "macros.yaml"
    macro_path.write_text(
        "macros:\n  simple:\n    when: bankroll_after < $x\n    action: regress\n"
    )
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text("use: simple\nparams:\n  x: 200")
    builder = RuleBuilder(macros_file=macro_path)
    expanded = builder.expand(spec_path)
    assert "bankroll_after < 200" in json.dumps(expanded)


def test_lint_flags_unknown_var():
    builder = RuleBuilder()
    bad = [{"id": "R1", "when": "weird_var < 10", "action": "regress"}]
    warnings = builder.lint(bad)
    assert any("unknown variable" in w.lower() for w in warnings)


def test_lint_flags_unknown_action():
    builder = RuleBuilder()
    bad = [{"id": "R2", "when": "bankroll_after < 10", "action": "explode"}]
    warnings = builder.lint(bad)
    assert any("unknown action verb" in w.lower() for w in warnings)
