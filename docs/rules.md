# Rules Engine (MVP)

**Status:** Phase 4 — Checkpoint 1 complete (parser + safe evaluator in place).  
This document describes how to author rules for CrapsSim‑Control and what the runtime supports today.

## Quick Start

Add a `rules` array at the top level of your strategy spec:

```jsonc
{
  "modes": {"base": { "template": "starter" }},
  "run": {"csv": true},
  "variables": {"units": 10},
  "rules": [
    {
      "name": "Clear 6&8 after 3 rolls",
      "on": {"event": "roll"},
      "when": "rolls_since_point >= 3 and point in (4,5,6,8,9,10)",
      "do": ["clear place_6", "clear place_8"]
    },
    {
      "name": "Switch to press mode on hot table",
      "on": {"event": "point_established"},
      "when": "streak >= 3",
      "do": ["switch_mode press"]
    }
  ]
}
```

## Events

Use `on.event` to gate a rule to one of:
- `comeout`
- `point_established`
- `roll`
- `seven_out`

If `on` is omitted, the rule is eligible on **all** events.

## Predicates (`when`)

`when` is a boolean expression evaluated by the sandbox in `crapssim_control.eval`.  
It can reference the merged context of controller state and current event:

- `on_comeout` (bool)
- `point` (int or `None`)
- `rolls_since_point` (int)
- `streak` (int; hot hand heuristic if present in your spec/state)
- `units` (from `spec.variables` if provided)
- all fields in the incoming `event` (e.g., `type`, `roll`, `point`).

### Supported operators

- arithmetic: `+ - * / // % **`
- comparisons: `== != < <= > >=`
- boolean: `and or not`
- membership: `in`, `not in` for tuples/lists like `point in (6,8)`
- ternary: `A if cond else B`

Function calls are **blocked** by default; only whitelisted math helpers (`abs`, `min`, `max`, `round`, selected `math.*`) are allowed.

## Actions (`do`)

Each step in `do` may be either a string or an object.

### String steps

```
set <bet> <amount>
clear <bet>
press <bet> <amount>
reduce <bet> <amount>
switch_mode <mode_name>
```

Examples:
- `set place_6 units*2`
- `clear place_8`
- `press odds_pass 10`
- `switch_mode base`

### Object steps

```json
{ "action": "set", "bet": "place_6", "amount": "units*2" }
```

## Envelope Contract

Each fired step becomes an Action Envelope as defined in `actions.py`:
```json
{
  "source": "rule",
  "id": "rule:Clear 6&8 after 3 rolls",
  "action": "clear",
  "bet_type": "place_6",
  "amount": null,
  "notes": ""
}
```

## Controller Integration

Rules are evaluated for every event (`comeout`, `point_established`, `roll`, `seven_out`).  
Controller merges rule‑driven envelopes **after** template/regression actions and before journaling.

## Testing

See `tests/test_rules_mvp.py` and `tests/test_rules_events.py` for examples that cover:
- event gating
- predicate filtering
- action string and object forms
- switch_mode behavior

## Roadmap (Phase 4)

- C2: richer event payloads & guardrails (done if tests present)
- C3: extended step set (parlay, lay, take odds helpers)
- C4: integration tests across controller state transitions
- C5: doc & regression pass (this file)
