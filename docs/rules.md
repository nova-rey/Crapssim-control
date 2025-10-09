⸻


# CrapsSim-Control — Rules Specification (P4C3)

This document defines the **runtime rules specification** used by `CrapsSim-Control`
to convert declarative rule logic into *action envelopes* during simulation.

---

## 1️⃣ Overview

Each Control spec defines three core blocks:

| Key | Type | Purpose |
| --- | ---- | -------- |
| `table` | object | Environment configuration (bubble table, level, bankroll hints, etc.) |
| `modes` | object | Named betting templates (default “Main”) |
| `rules` | array | Event-driven conditional actions |
| *(optional)* `table_rules` | object | Per-casino enforcement limits & increments |

During simulation, incoming table events (`roll`, `point_established`, `seven_out`, etc.)
are **canonicalized** and then evaluated against the spec by the runtime rules engine.

---

## 2️⃣ Canonical Event Types

These are the normalized `event.type` values recognized by the control layer:

comeout
point_established
roll
seven_out
shooter_change
bet_resolved

Additional fields may accompany events:
```json
{
  "type": "roll",
  "roll": 8,
  "point": 6,
  "on_comeout": false
}


⸻

3️⃣ Rule Object Schema

Each rule object must contain:

on:
  event: roll                # one of the canonical types
when: "roll == 8"            # (optional) boolean expression
do:                          # list of string or object steps
  - "press place_8 6"
  - { action: "clear", bet: "place_6" }

3.1 on.event

A string gating which event triggers this rule.
Validation enforces membership in the canonical event list.

3.2 when (optional)

A string expression evaluated with the safe evaluator against a merged context of
state ⊕ event.
Example: "on_comeout or point == 6"

If the expression raises or returns False, the rule is skipped.

3.3 do

An ordered list of actions, evaluated sequentially.
Each element can be a string or an object form.

⸻

4️⃣ Action Step Forms

4.1 String Form

Compact, space-delimited form:

Example	Meaning
set place_6 12	Set the Place 6 bet to 12 units
press place_6 6	Increase Place 6 by 6
reduce place_8 6	Decrease Place 8 by 6
clear place_6	Remove the Place 6 bet
switch_mode Aggressive	Switch controller to Aggressive mode

String steps that contain parentheses (e.g. apply_template('Main')) are treated as free-form directives and bypass validation.
Legacy starters like units 10 are also permitted.

Unknown verbs in a <verb> <bet> <amount> shape are flagged as validation errors.

⸻

4.2 Object Form

Verbose, explicit structure:

{ action: "set", bet_type: "place_6", amount: 12 }
{ action: "press", bet: "place_6", amount: "units / 2" }
{ action: "switch_mode", mode: "Main" }

Field	Type	Required	Notes
action	string	✅	One of: set, clear, press, reduce, switch_mode
bet / bet_type	string	⚙️	Required for all except switch_mode
amount	number | expr	⚙️	Required for set/press/reduce
mode	string	✴️	Optional, only for switch_mode
notes	string	✴️	Free-form context info

Numeric expressions are evaluated safely by eval_num() in a sandboxed namespace containing:
	•	current controller state (point, on_comeout, rolls_since_point, etc.)
	•	table configuration (level, bubble, etc.)
	•	user variables (units, mode, etc.)
	•	the current event dictionary

⸻

5️⃣ Validation Rules

Validation is performed by spec_validation.validate_spec() and enforces:
	•	required top-level sections: table, modes, rules
	•	all on.event values are canonical
	•	all when values are strings (if present)
	•	all do lists contain only strings or objects
	•	string steps:
	•	allowed if they contain parentheses (e.g. function-style)
	•	allowed if they start with a free-form starter like units
	•	otherwise, if shaped like <word> <word> <num> and verb is unknown → error
	•	object steps:
	•	action ∈ { set, clear, press, reduce, switch_mode }
	•	bet required for all except switch_mode
	•	amount required and numeric/expr for actions that need it

⸻

6️⃣ Action Envelopes

All actions emitted by templates or rules conform to this locked schema:

Key	Type	Example
source	"template" | "rule"	"rule"
id	string	"rule:#2" or "template:Main"
action	string	"set"
bet_type	string | None	"place_6"
amount	float | None	12.0
notes	string	"auto-regress after 3rd roll"

Future versions may add additive fields (e.g. seq), but existing columns remain stable.

⸻

7️⃣ CSV Journaling (Quick Reference)

When enabled via spec.run.csv, each event writes one row per Action Envelope with this exact schema:

ts, run_id, seed,
event_type, point, rolls_since_point, on_comeout,
mode, units, bankroll,
source, id, action, bet_type, amount, notes,
extra

	•	UTC timestamps (ts) for deterministic sorting
	•	extra field merges snapshot hints (roll, event_point, seq, custom extras`)

⸻

8️⃣ Versioning Notes

Phase	Focus	Highlights
P4C1	Spec guardrails	Basic shape validation & canonical event checks
P4C2	Canonical events	Consistent event normalization across rules / journal
P4C3	Rule runtime & journaling polish	Safe eval, free-form do steps, extra merge in CSV


⸻

Schema version: P4C3 · Oct 2025
Maintainer: CrapsSim-Control Core Team

---