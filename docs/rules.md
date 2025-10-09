# Rules Engine (MVP → P4C2)

**Status:** Phase 4 – Checkpoint 2  
Rules are evaluated at each canonical event with a safe expression sandbox. Outputs are normalized **Action Envelopes** (see `actions.py`).

---

## Quick Start

Add a `rules` array at the top level of your strategy spec:

```jsonc
{
  "modes": { "base": { "template": { "pass": "units", "place": { "6": "units*2", "8": "units*2" } } } },
  "variables": { "units": 10 },
  "rules": [
    {
      "name": "Regress 6/8 after 3 rolls",
      "on": { "event": "roll" },
      "when": "point in (4,5,6,8,9,10) and rolls_since_point >= 3",
      "do": ["clear place_6", "clear place_8"]
    },
    {
      "name": "Switch to press mode on hot table",
      "on": { "event": "point_established" },
      "when": "streak >= 3",
      "do": ["switch_mode Press"]
    }
  ]
}


⸻

Canonical Events

All inbound events are normalized by events.canonicalize_event(). The controller uses these when calling the rules engine.

Type	Guaranteed Keys (subset)	Example
comeout	type, event, roll (0 if unknown), point=None, on_comeout=True	{ "type":"comeout" }
point_established	type, event, point, on_comeout=False	{ "type":"point_established", "point":6 }
roll	type, event, roll, point (if on), on_comeout	{ "type":"roll", "roll":8, "point":6, "on_comeout":false }
seven_out	type, event, point (the previous point), on_comeout=True after reset	{ "type":"seven_out", "point":6 }

Valid values for on.event: comeout, point_established, roll, seven_out.
(Invalid values are rejected during spec validation.)

⸻

Evaluation Context

Every rule’s when expression is evaluated in a sandbox with a flat namespace built from controller state and the current event:

Common keys you can reference:
	•	on_comeout (bool)
	•	point (int or None)
	•	roll (int; for roll events)
	•	rolls_since_point (int; controller counter)
	•	mode (current mode name, if set)
	•	Any other simple keys the controller/state provides (e.g., units, streak)

We also provide read-only variables and event objects for parity with documentation, but attribute/subscript access is blocked by design. Prefer flat keys (point, roll, etc.).

Allowed operators & calls
	•	Arithmetic: + - * / // % **
	•	Comparisons: == != < <= > >=
	•	Boolean: and or not
	•	Membership: in, not in (with tuple literals, e.g., point in (6,8))
	•	Ternary: A if cond else B
	•	Calls (whitelisted only): min, max, abs, round, int, float, floor, ceil, sqrt, log, log10

No attribute access, indexing, or arbitrary function calls are allowed.

⸻

Actions (do)

Rules emit Action Envelopes via string or object steps.

String form

set <bet> <amount>
clear <bet>
press <bet> <amount>
reduce <bet> <amount>
switch_mode <ModeName>

Examples
	•	set place_6 units*2
	•	clear place_8
	•	press odds_pass 10
	•	switch_mode Base

Object form

{ "action": "set", "bet": "place_6", "amount": "units*2" }

Object keys:
	•	action: "set" | "clear" | "press" | "reduce" | "switch_mode"
	•	bet or bet_type: string (required for all except switch_mode)
	•	amount: number or string expression (required for set/press/reduce)
	•	mode: string (optional target for switch_mode), or use notes
	•	notes: string (optional)

⸻

Action Envelope Contract (output)

Each step becomes a normalized envelope (see actions.py):

{
  "source": "rule",
  "id": "rule:Regress 6/8 after 3 rolls",
  "action": "clear",
  "bet_type": "place_6",
  "amount": null,
  "notes": ""
}

	•	source: always "rule" here
	•	id: "rule:<name>" or "rule:#<index>"
	•	action: one of the supported verbs
	•	bet_type: string or null (for switch_mode)
	•	amount: number or null (for clear / switch_mode)
	•	notes: free text or mode name

⸻

Validation & Guardrails (P4C2)

Spec validation (spec_validation.py) enforces:
	•	rules must be an array of objects.
	•	rules[*].on must be an object with event in the canonical set.
	•	rules[*].when (if present) must be a string.
	•	rules[*].do must be an array of strings or objects.
	•	Object steps must include action, and when required, a non-empty bet/bet_type and an amount (number or expression) for set/press/reduce.

Controller behavior:
	•	Events are canonicalized before rule evaluation.
	•	Rule envelopes are appended after template/regression actions and then journaled.

Failure mode:
	•	Rule/eval errors fail quietly (rule simply doesn’t fire).
	•	Spec shape errors are hard errors surfaced by validation.

⸻

Cookbook

Press place-6 by 6 on every roll after the 2nd roll on a point:

{
  "name": "Press 6 after 2 rolls",
  "on": { "event": "roll" },
  "when": "point and rolls_since_point >= 2",
  "do": ["press place_6 6"]
}

Switch to “Conservative” mode after seven-out:

{
  "name": "Chill after PSO",
  "on": { "event": "seven_out" },
  "do": ["switch_mode Conservative"]
}

Set odds on pass to 2× units when point is 6 or 8:

{
  "name": "2x odds on 6/8",
  "on": { "event": "point_established" },
  "when": "point in (6,8)",
  "do": [{ "action": "set", "bet": "odds_pass", "amount": "units*2" }]
}


⸻

Testing References
	•	tests/test_rules_mvp.py – basic gating, predicates, and steps
	•	tests/test_rules_events.py – event-driven behavior across types
	•	(P4C2 additions recommended)
	•	tests/test_rules_event_context.py – context keys present/usable
	•	tests/test_rules_guardrails.py – validation errors for malformed rules
	•	tests/test_controller_event_payloads.py – controller emits canonical events

⸻

Notes & Roadmap
	•	P4C3: extend step set (parlay/lay/take-odds helpers that compile to primitives).
	•	P4C4: integration tests across longer hand flows (mode switches, regressions).
	•	P4C5: doc polish + rule examples for common strategies.