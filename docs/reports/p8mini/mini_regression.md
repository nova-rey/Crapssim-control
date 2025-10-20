# P8·C5b Mini Regression — Effect Logging & Live Odds Wiring

## Environment
- Fresh virtualenv with `pip install -e .` and CrapsSim git dependency.
- Full package list captured in [`env_freeze.txt`](env_freeze.txt).

## Effect summary check
```json
{
  "lines": 2,
  "all_have_verb": true,
  "all_have_schema": true,
  "stable_keys_ok": true
}
```

## Live line / odds wiring
- Snapshots stored in `snap_after_line.json`, `snap_after_set_odds.json`, `snap_after_take_odds.json`.
```json
{
  "bets_pass_ge_10": true,
  "point_value": 6,
  "point_value_valid": true,
  "roll_result": {
    "dice": [
      3,
      3
    ],
    "pso": false,
    "snapshot": {
      "bankroll": 990.0,
      "bankroll_after": 990.0,
      "bet_types": {},
      "bets": {
        "10": 0.0,
        "4": 0.0,
        "5": 0.0,
        "6": 0.0,
        "8": 0.0,
        "9": 0.0,
        "dont_pass": 0.0,
        "pass": 10.0
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
      "on_comeout": false,
      "point_on": true,
      "point_value": 6,
      "pso_flag": false,
      "rng_seed": 0,
      "roll_in_hand": 0,
      "total": null,
      "travel_events": {}
    },
    "status": "ok",
    "total": 6
  },
  "set_odds_bankroll_delta": -20.0,
  "set_odds_bankroll_delta_negative": true,
  "snapshot_set_odds_pass": 20.0,
  "snapshot_set_odds_pass_ge_20": true,
  "snapshot_take_bets_pass": 10.0,
  "snapshot_take_odds_pass": 10.0,
  "snapshot_take_odds_pass_between_10_20": true,
  "take_odds_bankroll_delta": 10.0,
  "take_odds_bankroll_delta_positive": true
}
```

## Parity sanity
```json
{
  "rolls": 8,
  "bankroll_end_live": 1000.0,
  "bankroll_end_replay": 1000.0,
  "equal": true
}
```

## Verdict
Effect summaries retain verb/schema with stable keys and live engine odds transitions mirror bankroll/snapshot changes. Live vs replay bankrolls match.
