# DSL Templates Reference (updated)

| Template | Description | Example |
|-----------|------------|---------|
| `press_on_hit` | Press a number when it just hit | `WHEN bets.6 > 0 AND last_hit == 6 THEN press(number=6)` |
| `regress_on_drawdown` | Regress when drawdown exceeds limit | `WHEN drawdown > 200 THEN regress()` |
| `lay_pull_on_point` | Take down a lay when the point matches | `WHEN point_on AND lays.10 > 0 AND point_value == 10 THEN take_down(number=10)` |
| `odds_on_point` | Add odds when point is on and none working | `WHEN point_on AND odds.4 == 0 AND point_value == 4 THEN set_odds(number=4, multiple=1)` |
| `set_come_odds_on_travel` | Add come odds after travel if none | `WHEN come_flat.6 > 0 AND odds.come.6 == 0 THEN set_odds(on=come, point=6, amount=30)` |
| `pull_dc_between_rolls` | Pull DC flat between rolls (legal window) | `WHEN dc_flat.8 > 0 AND NOT point_on THEN cancel_bet(family=dc, target=8)` |

> Use `csc dsl list` to view templates, and `csc dsl new <template> key=value` to scaffold rules.
