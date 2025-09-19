# Contributing

Thanks for helping improve **Crapssim-control**!  
This doc summarizes the project’s behavior contracts, test expectations, and coding conventions, so your changes stay green.

—

## 0) Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e “.[dev]”   # or pip install -r requirements-dev.txt if present
pytest -q


⸻

1) Repo Shape (high level)
	•	crapssim_control/
	•	controller.py – strategy orchestration (snapshots → events → rules → intents → materialization)
	•	engine_adapter.py – glue to a table/engine; runs roll loops safely
	•	events.py – derive_event(prev, curr): converts snapshots into a single high-level event
	•	rules.py – rules runner entrypoint used by controller
	•	materialize.py – applies bet intents to a player/table
	•	spec.py – spec validation (friendly messages that tests assert on)
	•	snapshotter.py – thin dataclasses/structs used by tests (GameState, TableView, PlayerView)
	•	telemetry.py – optional CSV logging
	•	varstore.py – variables, system counters (e.g., rolls since point)
	•	tests/ – authoritative contracts

⸻

2) Golden Contracts (tests rely on these)

A) Event detection (highest leverage)

Function signature:

derive_event(prev: dict | None, curr: dict) -> dict

	•	Accepts plain dict snapshots (controller ensures this). Some tests may construct objects; the controller and snapshot helpers normalize to dicts before calling derive_event.
	•	Priority (very important):
	1.	If the current roll just established a point → return {“event”: “point_established”, “point”: <number>}
	2.	Else if we are transitioning into comeout (or first observation is on comeout) → {“event”: “comeout”}
	3.	Else if the point was just made → {“event”: “point_made”}
	4.	Else if seven out happened → {“event”: “seven_out”}
	5.	Else emit the neutral tick: {“event”: “roll”}

Keep this conservative; specific bet results are emitted by the engine/adapter and fed to rules separately.

B) Controller <-> Rules <-> Materialization
	•	Controller calls:

intents = run_rules_for_event(spec, varstore, event)
rendered = render_template(spec, varstore, intents, table_level)
apply_intents(player, rendered, odds_policy=...)


	•	Render/Apply signatures:
	•	render_template(spec, varstore, intents, table_level: int)
table_level must be passed (usually spec[“table”][“level”]).
	•	apply_intents(player, intents, *, odds_policy=None)
Order matters: first arg is the player (or player-like), second is an iterable of intents.
	•	ControlStrategy.after_roll(table) exists and takes only the table (no event arg). It may inspect bankroll deltas, etc.

C) Engine Adapter (no infinite loops)
	•	The adapter drives rolls and must never hang. It enforces a maximum rolls per shooter (e.g., 200) as a safety cap. If no end-of-hand signal appears, it advances anyway.
	•	Typical flow per roll:
	1.	strategy.update_bets(table) (pre-roll placements)
	2.	Roll once via table.roll_once(), table.roll(), or table.step() (best-effort compatibility)
	3.	strategy.after_roll(table) (bankroll deltas etc.)
	4.	Build prev/curr snapshots, then call derive_event(prev, curr)
	5.	Run rules → render → apply

D) Spec Validation (human-friendly messages)
	•	validate_spec(spec) returns (ok: bool, errors: list[str]) without raising, except for truly unexpected cases.
	•	Tests assert on specific phrases. When you add or change validation, keep wording consistent.

Messages tests look for (examples):
	•	CLI stderr contains: Failed validation: ...
	•	Missing modes: includes modes section is required
	•	Missing template in a mode: includes template is required
	•	template.place wrong type: includes must be an object mapping numbers to expressions
	•	table.level wrong type: includes table.level must be integer
	•	Rules do items wrong type: includes do must be a list of strings
	•	Invalid on.event: error mentions allowed set (e.g., comeout, point_established, roll, seven_out, shooter_change, bet_resolved)

Tip: it’s fine to collect multiple errors and join them with ;  in the CLI output.

E) Telemetry
	•	Constructor should be called with a real path, not None, or else the module will try to os.makedirs(dirname(None)) and crash.
	•	Default behavior in controller: if no telemetry is provided, construct a harmless default like:

Telemetry(csv_path=“telemetry.csv”)


	•	Do not pass an enabled= kwarg unless telemetry.py supports it.

F) Imports and names
	•	The controller imports the rule runner from rules.py:

from .rules import run_rules_for_event

Don’t import from a stale module name (e.g., runner), or tests will fail on import.

⸻

3) Snapshot Expectations
	•	The controller’s _snapshot_from_table returns dicts for both “prev” and “curr”.
	•	Snapshots should include:
	•	comeout: bool
	•	point_on: bool
	•	point_number: int | None
	•	just_established_point: bool (when a point was just set)
	•	just_made_point: bool (when the point was just hit)
	•	just_seven_out: bool
	•	Dice/total info as needed by tests (e.g., total, dice)
	•	VarStore.refresh_system(curr) updates counters like rolls_since_point based on curr.

⸻

4) Error Handling Patterns
	•	Prefer graceful returns over raising during validation and non-critical flows.
	•	Raise only when continuing is unsafe (e.g., adapter can’t find a roll function on the table).
	•	Where possible, normalize inputs (objects → dicts) at the boundaries.

⸻

5) Style & Structure
	•	Keep modules focused and small. It’s fine if some files get shorter—less duplication, fewer branches.
	•	Prefer pure functions and explicit params (e.g., pass table_level).
	•	Tests are the source of truth for wording and behavior. If a test checks a phrase, adopt that phrase.

⸻

6) Common Pitfalls (and how to avoid them)
	•	“GameState has no attribute get”
Ensure anything passed into derive_event() is a dict (normalize beforehand).
	•	Events returning roll when tests expect comeout/point_established
Double-check the priority order (see Section 2A).
	•	Telemetry crashes on None path
Use a default file path; avoid None.
	•	Argument order to apply_intents
Must be apply_intents(player, intents, odds_policy=...), not swapped.
	•	Hanging tests
Keep the roll cap in the adapter.
	•	Import errors
Import from .rules, not .runner.

⸻

7) Commit Checklist

Before pushing:
	•	pytest -q is green locally.
	•	If you changed validation, re-run tests that assert specific messages.
	•	If you changed event logic, verify the priority still matches Section 2A.
	•	If you touched controller/adapter, verify:
	•	render_template(..., table_level=spec[“table”][“level”]) is passed
	•	apply_intents(player, intents, odds_policy=...) order is correct
	•	after_roll(table) signature matches controller
	•	roll cap still enforced
	•	No new None paths passed to Telemetry.

⸻

8) Adding/Updating Tests
	•	Prefer small, isolated tests that exercise one contract (e.g., specific validation message, specific event priority).
	•	For adapter smoke tests, seed a simple bet and rely on the roll cap to guarantee termination.

⸻

9) Questions

Open an issue or start a discussion in the repo. Please include:
	•	What you changed
	•	The failing test name(s)
	•	The exact error output (copy/paste)

Thanks again for contributing! 🎲