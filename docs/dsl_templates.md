# DSL Templates Reference

This file lists the built-in DSL rule templates available in CSC.

| Template | Description | Example |
|-----------|--------------|----------|
| `press_on_hit` | Press a number when it just hit | `WHEN bets.6 > 0 AND last_hit == 6 THEN press(number=6)` |
| `regress_on_drawdown` | Regress when bankroll drawdown exceeds limit | `WHEN drawdown > 200 THEN regress()` |
| `lay_pull_on_point` | Take down a lay bet when the point matches that number | `WHEN point_on AND lays.10 > 0 AND point_value == 10 THEN take_down(number=10)` |
| `odds_on_point` | Place odds when point is on and no odds are working | `WHEN point_on AND odds.4 == 0 AND point_value == 4 THEN set_odds(number=4, multiple=1)` |

You can add your own templates under `crapssim_control/dsl_helpers.py`.
