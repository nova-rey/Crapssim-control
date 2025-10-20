# Phase 8.5 — Live Engine Verification (Post-Hotfix)

## 1) Environment

- Python: `Python 3.12.10`
- pip: `pip 25.0.1`
- CSC install: editable (`pip install -e .`)
- CrapsSim: `crapssim 0.3.2` (git install, see env freeze)

Full package lock: [`env_freeze.txt`](./env_freeze.txt)

## 2) Verb Smoke Results

Effect summaries captured in [`effect_summaries.jsonl`](./effect_summaries.jsonl):

```jsonl
{"step": "line_bet pass $10", "effect_summary": {"verb": "line_bet", "bankroll_delta": -10.0, "bets": {"pass": "+10"}}}
{"step": "set_odds pass $20", "effect_summary": {"verb": "set_odds", "bankroll_delta": -20.0, "bets": {"odds_pass": "+20"}}}
{"step": "take_odds pass $10", "effect_summary": {"verb": "take_odds", "bankroll_delta": 10.0, "bets": {"odds_pass": "-10"}}}
{"step": "remove_line {}", "effect_summary": {"verb": "remove_line", "bankroll_delta": 10.0, "bets": {"pass": "-10"}}}
```

Roll bridge note: a fixed `(3,3)` roll is recorded alongside the live engine state to anchor the point before odds verbs.

## 3) Live Snapshot

[`live_snapshot_after.json`](./live_snapshot_after.json) confirms the post-odds state:

```json
{
  "point_value": 6,
  "bets": {"pass": 10.0, "6": 10.0, "Odds": 10.0},
  "odds": {"pass": 10.0, "dont_pass": 0.0, "come": {...}, "dc": {...}},
  "bankroll": 958.0,
  "on_comeout": false
}
```

## 4) Replay Parity

[`replay_parity.json`](./replay_parity.json)

```json
{"rolls": 20, "bankroll_end_live": 1000.0, "bankroll_end_replay": 1000.0, "digests_equal": true}
```

## 5) Fallback Summary

[`fallback_summary.json`](./fallback_summary.json)

```json
{
  "rolls": 20,
  "bankroll_start": 1000.0,
  "bankroll_end": 1000.0,
  "bankroll_drawdown": 0.0
}
```

## 6) Perf Sniff

[`perf_sniff.json`](./perf_sniff.json)

```json
{
  "average_ms_per_run": 0.6506,
  "average_ops_per_sec": 30764.03,
  "runs": [ {"run": 1, "ops_per_sec": 30946.20}, ..., {"run": 5, "ops_per_sec": 31001.26} ]
}
```

## 7) Verdict

- ✅ Bankroll deltas for `line_bet`, `set_odds`, and `take_odds` are non-zero and mirror live bankroll movement.
- ✅ Snapshot shows `bets.pass > 0` and `odds.pass = 10.0` while the point is established on 6.
- ✅ Replay parity holds (`digests_equal: true`), with fallback stub remaining deterministic.
- ✅ No schema deviations or exceptions observed; perf stays sub-millisecond per 20-roll loop.
