# Crapssim-Control

**Runtime for conditional craps strategies.**

Crapssim-Control is a small Python library that executes rule-based strategy specs (JSON) on top of [CrapsSim](https://github.com/skent259/crapssim). It enables conditional logic (martingale, regression, mode switching) that the static v1 exporter cannot express.

—

## Features

- Event-driven rule engine (comeout, point established, rolls, seven-out, bet resolved, shooter change).
- Variable store with safe expression evaluation.
- Mode + template system for declarative bet layouts.
- Bet legalization consistent with real craps tables (bubble and standard).
- Odds support (Pass, Don’t Pass, Come, Don’t Come).
- Structured tests (pytest) and CI integration.
- Compatible with JSON specs exported from **crapssim-compiler** (Node-RED builder).

—

## Example

Strategy spec (JSON):

```json
{
  “meta”: { “version”: 0, “name”: “RegressionDemo” },
  “table”: { “bubble”: false, “level”: 10 },

  “variables”: { “units”: 5, “mode”: “Aggressive”, “rolls_since_point”: 0 },

  “modes”: {
    “Aggressive”: {
      “template”: {
        “pass”: “units”,
        “place”: { “6”: “units*2”, “8”: “units*2” }
      }
    },
    “Regressed”: {
      “template”: { “pass”: “units”, “place”: { “6”: “units”, “8”: “units” } }
    }
  },

  “rules”: [
    { “on”: { “event”: “point_established” }, “do”: [“rolls_since_point = 0”, “apply_template(‘Aggressive’)”] },
    { “on”: { “event”: “roll” }, “do”: [“rolls_since_point += 1”] },
    { “on”: { “event”: “roll” }, “if”: “rolls_since_point >= 3”, “do”: [“mode = ‘Regressed’”, “apply_template(mode)”] }
  ]
}