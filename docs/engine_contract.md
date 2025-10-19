# Engine Contract Specification (v1)

## Purpose
This document defines the contract between CrapsSim-Control (CSC) and any compliant craps engine.  
Its goal is to isolate CSC’s control logic from engine internals, ensuring deterministic and interchangeable integrations.

## Required Methods
### `start_session(spec: dict) -> None`
Initialize a simulation session using the provided spec.  
Called once per run before any rolls or actions.

### `step_roll(dice: tuple[int, int] | int) -> dict`
Advance the engine by one roll, using either a fixed dice tuple or a seed integer.  
Returns the resulting state snapshot.

### `apply_action(verb: str, args: dict) -> dict`
Apply a CSC-issued action (e.g. press, regress, switch_profile).  
Returns an engine-reported delta or confirmation.

### `snapshot_state() -> dict`
Return a normalized snapshot of engine state including bankroll, bets, point, and roll indices.

## State Schema
```yaml
state:
  bankroll: float
  point_on: bool
  point_value: int | null
  hand_id: int
  roll_in_hand: int
  bets: dict
  rng_seed: int
```

## Determinism

Same seed → identical outcomes and state transitions.
All random processes must derive from a reproducible seed recorded by CSC.

## Verb + Policy Framework

CSC actions use a small, extensible grammar:

- **Verbs**: `press`, `regress`, `same_bet`, `switch_profile`, `apply_policy`
- **Policies**: strategy implementations referenced by `apply_policy`, e.g. `martingale_v1`

### Action JSON (uniform)
```json
{
  "verb": "press",
  "target": {"bet": "6"},
  "amount": {"mode":"dollars","value": 6}
}
```

Policy JSON

```json
{
  "verb": "apply_policy",
  "policy": {"name":"martingale_v1","args":{"step_key":"6","delta":6,"max_level":3}}
}
```

## Effect Schema (1.0)

All actions (verbs/policies) must return a uniform effect summary:

| Field           | Type              | Notes                                      |
|-----------------|-------------------|--------------------------------------------|
| `schema`        | string            | Must be `"1.0"`                            |
| `verb`          | string            | Registered verb name or `"apply_policy"`   |
| `target`        | object            | Optional; verb-specific targeting          |
| `bets`          | object<string,str>| Deltas like `"+6"` or `"-12"`              |
| `bankroll_delta`| number            | Positive returns to bankroll; negative spends |
| `policy`        | string\|null      | Policy name for `apply_policy`             |

**Validation:** CSC now validates `effect_summary` before journaling; invalid entries raise `ValueError`.

> **Note:** External commands are validated with the same `effect_summary` schema (1.0) as rules-driven actions. Invalid effects are rejected before journaling.

> **Implementation note:**  
> All external command routes call a shared helper (`_validate_and_attach_effect`) which enforces `effect_summary` schema validation before journaling.

### Deprecations
- Legacy verb `"martingale"` → **deprecated**; prefer `{ "verb": "apply_policy", "policy": {"name": "martingale_v1", ...}}`.
- NullAdapter compatibility shims (`attach`, `attach_cls`, `play`) are deprecated and will be removed in Phase 8·C0.

## Capabilities & Tape Schema

### Capabilities Endpoint
`GET /capabilities` returns:

```json
{
  "schema_versions": {"effect": "1.0", "tape": "1.0"},
  "verbs": ["press","regress","same_bet","switch_profile","apply_policy"],
  "policies": ["martingale_v1"]
}
```

### Command Tape v2 (schema 1.0)

Tapes are versioned for replay parity:

```json
{
  "tape_schema": "1.0",
  "commands": [
    {"verb":"press","args":{"target":{"bet":"6"},"amount":{"mode":"dollars","value":6}}},
    {"verb":"apply_policy","args":{"policy":{"name":"martingale_v1","args":{"step_key":"6","delta":6,"max_level":3}}}}
  ]
}
```

Replay validates the schema and reproduces identical snapshots under the same seed.


## Adapter Selection & Seeding

CSC supports multiple adapter implementations, configured via `run.adapter` settings.

```yaml
run:
  adapter:
    enabled: false
    impl: "null"   # or "vanilla"
    seed: 12345
```

- When enabled=false, CSC uses NullAdapter (no engine calls).
- When enabled=true and impl="vanilla", CSC uses VanillaAdapter for CrapsSim-Vanilla integration.
- Seeds are recorded and passed to adapter instances for deterministic replay.

## Live Engine Wiring (Phase 8)

Phase 8 introduces an opt-in bridge between VanillaAdapter and a live CrapsSim engine. When
`run.adapter.live_engine` is enabled and the CrapsSim package is importable, VanillaAdapter:

- Instantiates the CrapsSim adapter discovered via `resolve_engine_adapter()`.
- Forwards `run.seed` (or any explicit adapter seed) to CrapsSim’s RNG.
- Normalizes the table/player snapshot emitted by the engine so controller analytics receive
  consistent bankroll/bet fields.
- Executes `press` and `regress` verbs through CrapsSim, computing effect deltas from the
  engine’s before/after state.
- Falls back to deterministic stub math when CrapsSim is unavailable or raises during wiring.

Example configuration:

```yaml
run:
  seed: 42
  adapter:
    enabled: true
    impl: vanilla
    live_engine: true
```

When CrapsSim is not installed the adapter silently reverts to its stub behavior, ensuring
replay parity and existing tests remain deterministic.

## Legality Boundary

CSC enforces timing, legality, and bet limits before calling the adapter.
The engine assumes received actions are valid.

## Extension Points

Optional future methods may include:
	•	audit_state() for validation snapshots
	•	metrics() for run telemetry
