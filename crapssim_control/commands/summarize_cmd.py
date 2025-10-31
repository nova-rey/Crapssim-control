import sys

from crapssim_control.summary.human_report import generate


def run(artifacts_dir: str, human: bool = False):
    if not human:
        # existing summarize flow (if any) should remain unchanged; for now just print a hint
        print("Use --human to generate a markdown report.")
        return 0
    try:
        path = generate(artifacts_dir)
        print(f"Human summary written to: {path}")
        return 0
    except Exception as e:
        print(f"Failed to summarize: {e}", file=sys.stderr)
        return 2
