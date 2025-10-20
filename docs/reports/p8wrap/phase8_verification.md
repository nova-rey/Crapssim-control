Phase 8 — Live Engine Verification

1) Environment
	• Python: 3.12.10
	• Pip: 25.0.1
	• CrapsSim install: pip git+skent259/crapssim (success)
	• Freeze: docs/reports/p8wrap/env_freeze.txt

2) Capabilities

```
{
  "policies": [
    "martingale_v1"
  ],
  "schema_versions": {
    "effect": "1.0",
    "tape": "1.0"
  },
  "verbs": [
    "apply_policy",
    "buy_bet",
    "come_bet",
    "dont_come_bet",
    "lay_bet",
    "line_bet",
    "move_bet",
    "place_bet",
    "press",
    "regress",
    "remove_come",
    "remove_dont_come",
    "remove_line",
    "same_bet",
    "set_odds",
    "switch_profile",
    "take_down",
    "take_odds"
  ]
}
```

3) Verb Smoke (engine-backed)
	• Actions executed (order shown above).
	• Last snapshot:

```
{
  "bankroll": 988.0,
  "bankroll_after": 988.0,
  "bet_types": {
    "8": "place"
  },
  "bets": {
    "10": 0.0,
    "4": 0.0,
    "5": 0.0,
    "6": 0.0,
    "8": 12.0,
    "9": 0.0,
    "dont_pass": 0.0,
    "pass": 0.0
  },
  "come_flat": {
    "10": 0.0,
    "4": 0.0,
    "5": 0.0,
    "6": 0.0,
    "8": 0.0,
    "9": 0.0
  },
  "dc_flat": {
    "10": 0.0,
    "4": 0.0,
    "5": 0.0,
    "6": 0.0,
    "8": 0.0,
    "9": 0.0
  },
  "dice": null,
  "hand_id": 0,
  "last_effect": {
    "bankroll_delta": 10.0,
    "bets": {
      "pass": "-10"
    },
    "policy": null,
    "schema": "1.0",
    "target": {},
    "verb": "remove_line"
  },
  "odds": {
    "come": {
      "10": 0.0,
      "4": 0.0,
      "5": 0.0,
      "6": 0.0,
      "8": 0.0,
      "9": 0.0
    },
    "dc": {
      "10": 0.0,
      "4": 0.0,
      "5": 0.0,
      "6": 0.0,
      "8": 0.0,
      "9": 0.0
    },
    "dont_pass": 0.0,
    "pass": 0.0
  },
  "on_comeout": true,
  "point_on": false,
  "point_value": null,
  "pso_flag": false,
  "rng_seed": 0,
  "roll_in_hand": 0,
  "total": null,
  "travel_events": {}
}
```

	• effect_summary lines written to effect_summaries.jsonl (schema should be "1.0" for each).

4) Live vs Replay Parity

```
{
  "rolls": 20,
  "bankroll_end_live": 1000.0,
  "bankroll_end_replay": 1000.0,
  "digests_equal": true,
  "digest_live": "9c93046948525a82e8bf0efb08e67afbc77940ee760d40fa969040e0946d0878",
  "digest_replay": "9c93046948525a82e8bf0efb08e67afbc77940ee760d40fa969040e0946d0878"
}
```

	• Expect digests_equal: true and identical bankroll_end values.

5) Fallback Control (engineless)

```
{
  "rolls": 20,
  "hands": 0,
  "psos": 0,
  "bankroll_start": 1000.0,
  "bankroll_end": 1000.0,
  "bankroll_peak": 1000.0,
  "bankroll_drawdown": 0.0,
  "snapshot_schema": "2.0",
  "roll_event_schema": "1.0",
  "engine_contract_version": "1.0"
}
```

6) Perf Sniff (sanity)

```
{
  "runs": 5,
  "rolls_per_run": 20,
  "avg_ms": 1.8571286000110376,
  "ops_per_sec": 10769.313444357667
}
```

7) Verdict
	• Pass if: no exceptions, parity true, snapshot fields present (point_value, on_comeout, bets, come_flat, dc_flat, odds), and artifacts exist.
