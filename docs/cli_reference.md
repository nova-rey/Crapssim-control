# CLI Reference

### Risk Policy & Enforcement Flags

| Flag | Description |
|------|--------------|
| `--max-drawdown <pct>` | Set maximum bankroll drawdown percentage before new bets are blocked. |
| `--max-heat <amount>` | Set maximum total active exposure allowed per roll. |
| `--bet-cap <bet:amount>` | Override cap for specific bet (repeatable). |
| `--recovery <mode>` | Choose recovery mode: `none`, `flat`, or `step`. |
| `--risk-policy <path>` | Load full risk policy file (YAML or JSON). |
| `--no-policy-enforce` | Disable blocking; policy logs only. |
| `--policy-report` | Include policy statistics in summary output. |
