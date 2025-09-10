# SPEC v0 (draft)

```json
{
  “meta”: { “version”: 0, “name”: “MyStrategy” },
  “table”: { “bubble”: false, “level”: 10 },
  “variables”: { “base_units”: 5, “units”: 5, “mode”: “Aggressive”, “rolls_since_point”: 0 },
  “modes”: {
    “Aggressive”: { “template”: { “pass”: “units”, “place”: { “6”: “units*2”, “8”: “units*2”, “5”: “units” }, “field”: “units” } },
    “Regressed”:  { “template”: { “pass”: “units”, “place”: { “6”: “units”,   “8”: “units” } } }
  },
  “rules”: [
    { “on”: {“event”:”point_established”}, “do”: [“rolls_since_point = 0”, “apply_template(‘Aggressive’)”] },
    { “on”: {“event”:”roll”},              “do”: [“rolls_since_point += 1”] },
    { “on”: {“event”:”roll”}, “if”:”rolls_since_point >= 3”, “do”:[“mode=‘Regressed’”,”apply_template(mode)”] }
  ]
}