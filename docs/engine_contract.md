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

Effect Summary (schema 1.0)

All handlers return:

```json
{
  "schema":"1.0",
  "verb":"<verb or apply_policy>",
  "target": {...},
  "bets": {"6":"+6"},
  "bankroll_delta": -6,
  "policy": "martingale_v1" | null
}
```

Back-compat: legacy verb "martingale" is an alias to apply_policy(policy="martingale_v1") during Phase 7.

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

## Legality Boundary

CSC enforces timing, legality, and bet limits before calling the adapter.
The engine assumes received actions are valid.

## Extension Points

Optional future methods may include:
	•	audit_state() for validation snapshots
	•	metrics() for run telemetry
