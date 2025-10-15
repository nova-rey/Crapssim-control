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

8. Update & Maintain

To update CSC later:

git pull
pip install -e .
 

⸻

✅ You now have Crapssim-Control running on Ubuntu.
You can validate specs, run strategies, and start building more complex rule-based systems.

⸻