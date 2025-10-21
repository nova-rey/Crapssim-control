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
