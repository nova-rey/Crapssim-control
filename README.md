⸻

crapssim-control

Runtime companion library for crapssim-compiler.
Provides a controller layer on top of CrapsSim that executes rule-based strategy specs (JSON) with conditional logic, state tracking, and mode switching.

⸻

✨ What it does
	•	Consumes strategy specs exported by crapssim-compiler (Node-RED visual builder).
	•	Tracks state (variables, counters, bankroll, roll history).
	•	Evaluates rules on events (comeout, point_established, roll, seven_out, bet_resolved, shooter_change).
	•	Executes actions: set/mutate variables, switch modes, regress/progress bet sizing, apply/clear bet templates.
	•	Applies templates as real CrapsSim bets (BetPassLine, BetPlace, BetField, etc.), respecting table rules.
	•	Supports bubble vs. live table increments (via built-in legalizer).

This makes it possible to author strategies like Martingale, regression, and conditional mode switches — things that static bet templates can’t handle.

⸻

📦 Installation

pip install crapssim-control

Requires:
	•	Python 3.9+
	•	CrapsSim (pip install crapssim)

⸻

🚀 Quick Start

import crapssim as craps
from crapssim_control import ControlStrategy

# Example: Pass Martingale (simplified spec)
SPEC = {
  "variables": { "base_units": 5, "units": 5, "mode": "PassOnly" },
  "modes": {
    "PassOnly": { "template": { "pass": "units" } }
  },
  "rules": [
    { "on": { "event": "comeout" }, "do": ["apply_template('PassOnly')"] },
    { "on": { "event": "bet_resolved", "bet_type": "pass" },
      "if": "event.result == 'lose' and event.reason == 'seven_out'",
      "do": ["units = min(units*2, base_units*8)"] },
    { "on": { "event": "bet_resolved", "bet_type": "pass" },
      "if": "event.result == 'win'",
      "do": ["units = base_units"] },
    { "on": { "event": "bet_resolved", "bet_type": "pass" }, "do": ["apply_template('PassOnly')"] }
  ],
  "table": { "bubble": false, "level": 10 }
}

if __name__ == "__main__":
    table = craps.Table(seed=42)
    strat = ControlStrategy(SPEC)
    table.add_player(strategy=strat, bankroll=300, name="Martingale")
    table.run(max_rolls=200, verbose=True)


⸻

📖 Spec Overview

A strategy spec has four parts:
	•	variables → initial state (units, mode, counters).
	•	modes → named bet templates (expressions in variables).
	•	rules → event triggers with optional conditions and actions.
	•	table → table rules (bubble, level).

See SPEC.md for the full contract.

⸻

🧪 Examples
	•	Martingale on Pass
	•	Regression after N rolls since point
	•	Switch to conservative mode on drawdown

See examples/ for ready-to-run specs.

⸻

🛠 Development

Clone and install locally:

git clone https://github.com/yourname/crapssim-control.git
cd crapssim-control
pip install -e .

Run tests:

pytest


⸻

🤝 Related Projects
	•	CrapsSim — simulation engine.
	•	crapssim-compiler — Node-RED strategy builder (exports specs consumed by this library).

⸻

📜 License

MIT

⸻
