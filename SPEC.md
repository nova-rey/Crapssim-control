—

### `SPEC.md`
```markdown
# Crapssim-Control Spec (v0)

This document defines the JSON contract shared between **crapssim-compiler** (exporter) and **crapssim-control** (runtime).

—

## Top-level schema

```json
{
  “meta”: { “version”: 0, “name”: “MyStrategy” },
  “table”: { “bubble”: false, “level”: 10 },

  “variables”: { “units”: 5, “mode”: “Aggressive” },

  “modes”: { ... },

  “rules”: [ ... ]
}