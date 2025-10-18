# Rules Engine Schema (v1)

## Rule Object
| Field | Type | Description |
|--------|------|-------------|
| id | string | Unique identifier |
| when | string | Boolean condition |
| scope | string | roll / hand / session |
| cooldown | string/int | How often rule may re-fire |
| guard | string | Extra conditional constraint |
| action | string | Placeholder action verb |
| enabled | bool | Whether rule is active |

## Allowed Variables
`bankroll_after`, `drawdown_after`, `hand_id`, `roll_in_hand`, `point_on`, `last_roll_total`, `box_hits[...]`, `dc_losses`, `dc_wins`.

## Behavior
Evaluator checks all enabled rules at each evaluation window and outputs a `decision_candidates.jsonl` file listing each rule and its fired status.
