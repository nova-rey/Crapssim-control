# run_demo.py
import sys
from pathlib import Path

try:
    from crapssim.table import Table
except Exception as e:
    print("CrapsSim engine not available.\n"
          "Install it first (one-time):\n"
          '  pip install "git+https://github.com/skent259/crapssim.git"\n'
          "Then re-run:\n"
          "  python run_demo.py [examples/regression.json]\n")
    sys.exit(1)

from crapssim_control import ControlStrategy
from crapssim_control.spec_loader import load_spec_file

def main(spec_path: str | None = None):
    spec_file = Path(spec_path or "examples/regression.json")
    if not spec_file.exists():
        print(f"SPEC not found: {spec_file}")
        sys.exit(2)

    spec, spec_deprecations = load_spec_file(spec_file)

    # Table & strategy
    table = Table()
    strat = ControlStrategy(spec, spec_deprecations=spec_deprecations)
    table.add_player(bankroll=300, strategy=strat, name="SpecBot")

    # Run a short session
    table.fixed_run(max_rolls=60, runout=False, verbose=False)

    # Report
    p = table.players[0]
    print(f"Final bankroll: ${getattr(p,'bankroll',0)}")
    # Show current bets snapshot (duck-typed)
    bets = getattr(p, "bets", [])
    if bets:
        print("Active bets:")
        for b in bets:
            kind = getattr(b, "kind", b.__class__.__name__)
            num = getattr(b, "number", None)
            amt = getattr(b, "amount", None)
            print(f" - {kind} {num or ''} = ${amt}")
    else:
        print("No active bets at end.")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)