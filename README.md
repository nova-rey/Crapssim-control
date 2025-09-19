# Crapssim-Control

A small control layer and CLI to define, validate, and run Craps betting strategies
against the CrapsSim engine.

- Validate a strategy spec (JSON **or** YAML).
- Run a simulation with your spec and get a quick result line.
- Keep your spec readable with variables, modes (templates), and rules.

## Install

```bash
pip install -e .
# (Optional engine for ‘run’): 
pip install “git+https://github.com/skent259/crapssim.git”

CLI

The tool installs as crapssim-ctl and can also be launched via python -m crapssim_control.

crapssim-ctl -h

Validate a spec

crapssim-ctl validate path/to/spec.json
# or
python -m crapssim_control validate path/to/spec.yaml

Success prints to stdout:

OK: path/to/spec.json

Failures print to stderr:

failed validation:
- Missing required section: ‘modes’
- You must define at least one mode.

Use -v/-vv for more verbose logging (mostly relevant to run):

crapssim-ctl -v validate examples/minimal.json

Run a quick simulation

Requires the CrapsSim engine.

crapssim-ctl -v run examples/minimal.json —rolls 200 —seed 123

Output (stdout) ends with a summary line:

RESULT: rolls=200 bankroll=1012.00

If the CrapsSim engine isn’t installed or available, you’ll get a helpful error:

failed: CrapsSim engine not available (pip install crapssim).

Spec format (quick tour)

A spec is a JSON or YAML object with:
	•	meta (optional): name, version
	•	table: { bubble: bool, level: int }
	•	variables: named values used in templates/rules (e.g. units, mode)
	•	modes: named templates mapping bet types to stake/objects
	•	rules: list of rule objects { “on”: {...}, “do”: [ ... ] }

Example (JSON):

{
  “meta”: {“version”: 0, “name”: “Minimal”},
  “table”: {“bubble”: false, “level”: 10},
  “variables”: {“units”: 10, “mode”: “Main”},
  “modes”: {
    “Main”: {
      “template”: {
        “pass”: “units”
      }
    }
  },
  “rules”: [
    {“on”: {“event”: “comeout”}, “do”: [“apply_template(‘Main’)”]}
  ]
}

The same in YAML (optional):

meta: {version: 0, name: Minimal}
table: {bubble: false, level: 10}
variables: {units: 10, mode: Main}
modes:
  Main:
    template:
      pass: units
rules:
  - on: {event: comeout}
    do: [“apply_template(‘Main’)”]

See SPEC.md for the full schema and examples.

Logging & verbosity
	•	-v sets INFO level logs, -vv sets DEBUG.
	•	Validation messages follow a fixed format so they’re easy to parse.
	•	Run’s logs (INFO/DEBUG) go to stderr; the final RESULT: line goes to stdout.

Examples
	•	examples/minimal.json
	•	examples/minimal.yaml

Policy & rules sanity checks

We maintain a short checklist of common table policies we aim to respect in specs/rules.
See docs/RULES_CHECKLIST.md.

Roadmap
	•	V1: ✅
	•	Batch 4 & 5 (feature flagged levers + live tuning hooks): post-V1, per plan.

License

MIT (see LICENSE)

—

**Project policies & release process:** see [`docs/POLICY.md`](docs/POLICY.md) and [`CHANGELOG.md`](CHANGELOG.md).
—