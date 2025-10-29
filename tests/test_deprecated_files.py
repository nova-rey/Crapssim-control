from pathlib import Path

import crapssim_control


def test_legacy_modules_removed():
    pkg_dir = Path(crapssim_control.__file__).resolve().parent
    removed = {
        "events_std.py",
        "materialize.py",
        "memory_rt.py",
        "snapshotter.py",
    }
    missing = {name for name in removed if not (pkg_dir / name).exists()}
    assert (
        missing == removed
    ), f"Expected all legacy modules to be absent, but found {removed - missing}"
