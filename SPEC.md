# CrapsSim Control Strategy Spec (v0)

This document describes the **JSON schema** used by CrapsSim Control to define betting strategies.  
Every strategy is expressed as a JSON file that follows this specification.  

The JSON is meant to be:
- **Declarative**: no Python logic, just structured data.
- **Composable**: easy for Node-RED or Evo to generate and mutate.
- **Executable**: consumed at runtime by `ControlStrategy` inside CrapsSim Control.

—

## Top-Level Shape

Every strategy spec is a JSON object with the following keys:

```json
{
  “meta”: { ... },
  “table”: { ... },
  “variables”: { ... },
  “modes”: { ... },
  “rules”: [ ... ]
}

	•	meta (optional but recommended)
Metadata about the strategy: name, version, author, description.
	•	table (required)
Table settings such as bubble mode and minimum level.
	•	variables (required)
Defines initial user-level variables available in expressions.
	•	modes (required)
Each mode contains a template (bets to place). Strategies can switch between modes dynamically.
	•	rules (required, can be empty)
Event→Action mappings. Rules drive conditional behavior.

⸻

Section Details

1. meta

“meta”: {
  “name”: “BasicPass”,
  “version”: 0,
  “author”: “example”,
  “description”: “Flat pass line strategy”
}

2. table

“table”: {
  “bubble”: false,
  “level”: 10
}

	•	bubble: true for $1 bubble craps tables (increments of 1), false for standard casinos.
	•	level: table minimum in dollars (e.g. 5, 10, 25).

3. variables

“variables”: {
  “units”: 10,
  “mode”: “Main”
}

	•	Arbitrary key→value pairs.
	•	Values may be numeric, strings, or booleans.
	•	These are accessible in templates and rule expressions.

4. modes

Each mode defines a betting template.

“modes”: {
  “Main”: {
    “template”: {
      “pass”: “units”,
      “place”: {
        “6”: “units * 2”,
        “8”: “units * 2”
      }
    }
  }
}

	•	Bet types: pass, dont_pass, come, dont_come, place, field, etc.
	•	Values are expressions resolved against variables.
	•	Place bets are keyed by number (“4”, “5”, “6”, “8”, “9”, “10”).

5. rules

Rules are event-driven. Each rule has an on condition and a do list of actions.

“rules”: [
  {
    “on”: { “event”: “comeout” },
    “do”: [“apply_template(‘Main’)”]
  },
  {
    “on”: { “event”: “bet_resolved”, “bet”: “pass”, “result”: “lose” },
    “do”: [“units *= 2”, “apply_template(‘Main’)”]
  },
  {
    “on”: { “event”: “bet_resolved”, “bet”: “pass”, “result”: “win” },
    “do”: [“units = 10”, “apply_template(‘Main’)”]
  }
]


⸻

Actions

Valid entries in the do array include:
	•	Assignments
“units = 10”
“units *= 2”
	•	Apply template
“apply_template(‘Main’)”
	•	Odds application
“apply_odds(‘come’, amount=25, scope=‘all’)”
“apply_odds(‘dont_pass’, amount=30)”
	•	Logging
“log(‘Switching to recovery mode’)”

⸻

Intents

After rules fire, they produce intents, which are normalized bet instructions:

(kind, number, amount, options)

Examples:
	•	(“pass”, None, 10, {})
	•	(“place”, 6, 24, {})
	•	(“__apply_odds__”, “come”, 25, {“scope”: “all”})

These intents are then legalized to fit table rules (increments, caps, bubble min, etc).

⸻

Telemetry

If telemetry is enabled, CrapsSim Control emits CSV logs of every hand/run:
	•	Roll logs: bankroll, deltas, point, shooter, events.
	•	Hand summaries: start/end bankroll, max drawdown, rolls, seven-outs.
	•	Run summary: final bankroll, peak, volatility, ruin flag.

This makes it easy to analyze results in Excel, R, or pandas.

⸻

Minimal Example

{
  “meta”: { “name”: “FlatPass”, “version”: 0 },
  “table”: { “bubble”: false, “level”: 10 },
  “variables”: { “units”: 10, “mode”: “Main” },
  “modes”: {
    “Main”: { “template”: { “pass”: “units” } }
  },
  “rules”: [
    { “on”: { “event”: “comeout” }, “do”: [“apply_template(‘Main’)”] }
  ]
}


⸻

Martingale Example

{
  “meta”: { “name”: “PassMartingale”, “version”: 0 },
  “table”: { “bubble”: false, “level”: 10 },
  “variables”: { “units”: 10, “base_units”: 10, “mode”: “Main” },
  “modes”: {
    “Main”: { “template”: { “pass”: “units” } }
  },
  “rules”: [
    { “on”: { “event”: “comeout” }, “do”: [“apply_template(‘Main’)”] },
    { “on”: { “event”: “bet_resolved”, “bet”: “pass”, “result”: “lose” },
      “do”: [“units = min(units * 2, base_units * 10)”, “apply_template(‘Main’)”] },
    { “on”: { “event”: “bet_resolved”, “bet”: “pass”, “result”: “win” },
      “do”: [“units = base_units”, “apply_template(‘Main’)”] }
  ]
}


⸻

Versioning
	•	Current spec version: 0
	•	Breaking changes will increment this number.
	•	meta.version should match the spec version the file was built for.

⸻