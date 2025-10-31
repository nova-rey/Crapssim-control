import json
import pathlib
from textwrap import dedent

SKELETON_SPEC = {
    "schema_version": "1.0",
    "table": {"min_bet": 5, "odds": "3-4-5x"},
    "profiles": {
        "default": {
            "bets": [
                {"type": "pass_line", "amount": 5},
            ]
        }
    },
    "modes": {"Default": {"template": {}}},
    "behavior": {"schema_version": "1.0", "rules": []},
    "rules": [],
    "run": {"strict": False, "demo_fallbacks": False, "csv": {"embed_analytics": True}},
}

README_QUICKSTART = dedent(
    """\
    # CSC Quickstart

    ## Fast path
    1) Validate your spec
       ```
       csc doctor --spec spec.json
       ```
    2) Run with explain stream
       ```
       csc run --seed 4242 --spec spec.json --explain
       ```
    3) Human summary
       ```
       csc summarize --artifacts artifacts/latest --human
       ```
    """
)


def run(target_dir: str):
    p = pathlib.Path(target_dir)
    p.mkdir(parents=True, exist_ok=True)
    (p / "spec.json").write_text(json.dumps(SKELETON_SPEC, indent=2))
    (p / "behavior.dsl.yaml").write_text("# WHEN <condition> THEN <verb>(args)\n")
    (p / "profiles").mkdir(exist_ok=True)
    (p / "recipes").mkdir(exist_ok=True)
    (p / "README_quickstart.md").write_text(README_QUICKSTART)
    print(f"Initialized CSC skeleton at: {p}")
