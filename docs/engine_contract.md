# Engine Contract — Vanilla Bet Coverage (Phase 9)

The CrapsSim-Control engine adapter now supports the full vanilla bet surface.

## Supported Bet Families

| Family | Verbs | Snapshot Keys | Notes |
|--------|--------|----------------|-------|
| Line / Come / DC | `line_bet`, `come`, `dont_come`, `set_odds`, `take_odds`, `remove_odds` | `line`, `come`, `dc`, `odds_*` | Includes come/DC odds and point-aware logic. |
| Place / Buy / Lay | `place_bet`, `buy_bet`, `lay_bet`, `take_down`, `move_bet` | `place_*`, `buy_*`, `lay_*` | Enforces correct unit increments and commission. |
| Field / Hardways | `field_bet`, `hardway_bet` | `field`, `hardway_*` | Full mid-table coverage. |
| Props (One-Roll) | `any7_bet`, `anycraps_bet`, `yo_bet`, `craps2_bet`, `craps3_bet`, `craps12_bet`, `ce_bet`, `hop_bet` | `props` | Auto-resolve after one roll. |
| Bonus | `ats_all_bet`, `ats_small_bet`, `ats_tall_bet` | `ats_*`, `ats_progress` | Tracks bonus progress and resolves at completion. |

## Schema Versions

| Schema | Version |
|---------|----------|
| Snapshot | 2.1 |
| Roll Event | 1.0 |
| Capabilities | 1.0 |
| Error Surface | 1.0 |
| Replay | 1.0 |

For verb and field examples, see `/examples/` and `README.md`.

### cancel_bet(family, target[, amount])
Universal alias to remove or turn off existing bets between rolls.

| family | target | effect |
|---------|---------|---------|
| place/buy/lay | number | remove bet or reduce amount |
| odds | ("come"|"dc"|"pass"|"dont_pass", point) | remove odds |
| hardway | number | remove hardway |
| dc/dont_pass | point | move DC/DP to off |
| field | "field" | clear field bet |

### Journal Explanations (why)

- Toggle: `run.journal.explain: true|false` (default: false)
- Grouping mode: `run.journal.explain_grouping: "first_only" | "ditto" | "aggregate_line"`

**Usage**
- Pass `_why` and `_why_group` in `args` to explicitly group actions.
- Or call `apply_actions([{verb,args}, ...], why="…", group_id="…")` to batch with a single explanation.

**CSV**
- Adds a `why` column when enabled.
- For grouped actions:
  - `first_only`: only the first row in the group carries the text.
  - `ditto`: first row carries the text; subsequent show `〃`.
  - `aggregate_line`: a synthetic `group_explain` row carries the text; action rows omit `why`.

### Policy Journal Fields

When policies are evaluated, CSC appends a `policy_eval` row to the journal with these additional fields:

- `policy_triggered`: comma-separated list (e.g., `drawdown_limit,bet_cap`)
- `risk_violation_reason`: short code when `allowed=false` under enforcement
- `adjusted_amount`: number, present when recovery modifies the bet
- `enforce`: true|false — whether enforcement was active this run

These rows are informational; actual bet effect rows remain unchanged except when a policy blocks an action (which returns a `status: rejected` result to the caller).

### Baseline Artifacts (Phase 11)

Baseline runs for DSL v1 produce:
- `baselines/phase11/journal.csv`
- `baselines/phase11/report.json`
- `baselines/phase11/manifest.json`
- `examples/demo_rules.dsl`

Schema tags used:
- `dsl_schema_version: "1.0"`
- `trace_schema_version: "1.0"`
