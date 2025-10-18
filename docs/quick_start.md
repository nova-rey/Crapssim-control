⸻

Crapssim-Control Quick Start (Ubuntu)

This guide walks you through installing and running Crapssim-Control (CSC) on a fresh Ubuntu system.

⸻

1. Prerequisites

Make sure your system is up to date and has Python:

sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git

Verify Python version (CSC supports Python 3.11+):

python3 —version


⸻

2. Clone the Repo

Download the CSC source code:

git clone https://github.com/nova-rey/Crapssim-control.git
cd Crapssim-control


⸻

3. Create a Virtual Environment

Set up a clean Python environment for CSC:

python3 -m venv .venv
source .venv/bin/activate

Upgrade pip:

pip install —upgrade pip


⸻

4. Install Crapssim-Control

From inside the repo:

pip install -e .

This installs CSC in editable mode, so local changes are picked up automatically.
It also installs the command-line tool crapssim-ctl.

⸻

5. (Optional) Install CrapsSim Engine

CSC can run without CrapsSim for validation only, but to actually simulate rolls, install CrapsSim:

pip install crapssim

> Demo compatibility: The demo uses an adaptive shim for `Table.fixed_run` that supports engines requiring `seed=` or `rng=`, and engines that require `dice_outcomes=`. When `dice_outcomes` is required, the shim auto-generates deterministic fair dice from your seed (or a default).


⸻

6. Validate a Spec

Create a simple spec file (e.g. martingale.json):

{
  “meta”: {“version”: 0, “name”: “Martingale”},
  “table”: {“bubble”: false, “level”: 10},
  “variables”: {“units”: 10, “mode”: “Main”},
  “modes”: {
    “Main”: {
      “template”: {“pass”: “units”}
    }
  },
  “rules”: [
    {“on”: {“event”: “comeout”}, “do”: [“apply_template(‘Main’)”]}
  ]
}

Validate it:

crapssim-ctl validate martingale.json

If successful, you’ll see:

OK: martingale.json


⸻

7. Run a Simulation

With CrapsSim installed:

crapssim-ctl run martingale.json —rolls 1000

You should see output like:

RESULT: rolls=1000 bankroll=1235.00


⸻

New Defaults

The runtime keeps demo fallbacks disabled unless you explicitly opt in. If your spec
relies on demo-mode helper bets, set `run.demo_fallbacks` to `true` or pass
`--demo-fallbacks` when running. Validation runs now operate in Advisory mode by
default (`run.strict=false`), so you receive non-blocking advisories instead of
halting. Enable Guardrails with `--strict` (or `run.strict=true`) when you want strict
enforcement.


⸻

Command-Line Flags

`crapssim-ctl` exposes explicit switches for common runtime options:

* `--demo-fallbacks` enables demo helper bets for that run (default OFF).
* `--strict` enables Guardrails (strict validation). Leave it unset to stay in
  Advisory mode.
* `--no-embed-analytics` disables CSV analytics embedding. Omit the flag (or set
  `run.csv.embed_analytics=true`) to keep analytics columns.

> Outputs now include schema version labels (journal_schema_version and summary_schema_version) to help external tools verify compatibility.


⸻

8. Update & Maintain

To update CSC later:

git pull
pip install -e .
 

⸻

✅ You now have Crapssim-Control running on Ubuntu.
You can validate specs, run strategies, and start building more complex rule-based systems.

⸻