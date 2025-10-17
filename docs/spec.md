# Strategy SPEC Format

This document explains the JSON strategy format (“SPEC”) used by `crapssim_control`.  
A SPEC describes **table settings**, **variables**, **modes** with **templates**, and **rules** that react to events.

—

## Top-Level Keys

- **meta**: Free-form info about the strategy
  ```json
  { “version”: 0, “name”: “Martingale Pass” }

	•	table: Table/runtime configuration your strategy expects

{
  “bubble”: false,
  “level”: 10,
  “odds_policy”: “3-4-5x”
}


	•	variables: Initial user-tunable variables

{
  “base_units”: 10,
  “units”: 10,
  “cap_mult”: 4,
  “mode”: “Main”
}


	•	modes: Named “loadouts” of templates

{
  “Main”: {
    “template”: {
      “pass”: “units”
    }
  }
}


	•	rules: If-this-then-that style reactions to events

[
  { “on”: { “event”: “comeout” },
    “do”: [“apply_template(‘Main’)”] },

  { “on”: { “event”: “bet_resolved”, “bet”: “pass”, “result”: “lose” },
    “do”: [“units = min(units * 2, base_units * cap_mult)”,
           “apply_template(‘Main’)”] }
]



⸻

Run Configuration (`run`)

The optional `run` section lets you override controller defaults. Key fields include:

- `demo_fallbacks`: Enables demo-mode helper bets when `true`. Defaults to `false`, so specs that rely on fallback bets must opt in.
- `strict`: Enables Guardrails (strict validation) when `true`. The default is Advisory mode (`false`), which logs advisories while continuing execution.
- `csv.embed_analytics`: Controls whether CSV sinks include embedded analytics payloads. Defaults to `true`; set to `false` (or use CLI `--no-embed-analytics`) to slim down CSV outputs.

⸻

Templates

A template is a mapping of bet names to expressions that evaluate to dollar amounts.
Examples:

{
  “pass”: “10”,
  “place_5”: “5”,
  “place_6”: “6”,
  “place_8”: “6”
}

	•	Values are expressions evaluated by the safe evaluator (e.g., units * 2, min(units, 30)).
	•	The controller converts the template into a concrete plan:

[
  {“action”: “set”, “bet_type”: “pass_line”, “amount”: 10.0},
  {“action”: “set”, “bet_type”: “place_5”, “amount”: 5.0}
]


	•	Setting a bet to 0 (or omitting it in the template) effectively means “do not set”.
The controller may also emit {“action”:”clear”, ...} when switching modes/templates.

Bet Keys (common):
	•	“pass” — Pass Line bet
	•	“place_N” — Place bet on number N (e.g., place_5, place_6, place_8)
	•	Additional keys follow the same pattern used in the codebase/tests.

⸻

Rules

Each rule has:
	•	on: a pattern to match incoming events (e.g., {“event”:”comeout”} or {“event”:”bet_resolved”,”bet”:”pass”,”result”:”lose”})
	•	do: a list of statements to execute in order.

Statements supported:
	•	Variable assignments: units = 10, units += 10, units = min(units * 2, 40)
	•	Template application: apply_template(‘Main’)

At runtime, the engine calls the rules runner with events like:

{“event”:”comeout”}
{“event”:”bet_resolved”,”bet”:”pass”,”result”:”win”}

When a rule matches, its do list is executed in order.
Applying a template produces intents that the controller turns into actions.

⸻

Safe Expressions

The evaluator supports:
	•	Basic math (+ - * / // % **) and comparisons
	•	Conditionals like 1 if bubble else 5
	•	A small set of safe functions: min, max, abs, round, int, float, floor, ceil

Unsafe operations like attribute access, imports, loops, or subscripts are blocked.

⸻

Example: Martingale Pass

See examples/specs/martingale_pass.spec.json.
It doubles the Pass Line bet on a loss (capped), and resets to base on a win.

⸻

Example: Regression After 3 Rolls

See examples/specs/regression_three_rolls.spec.json.
It starts with a broader layout and regresses to a leaner layout after the point is established or a reset event.

⸻

Authoring Tips
	•	Keep templates simple and declarative. Use variables for anything dynamic.
	•	Put your starting layout in a default mode (e.g., “mode”: “Main”).
	•	Use rules for event-driven changes (apply different templates, update variables).
	•	Prefer small, explicit steps so it’s easy to reason about and test.