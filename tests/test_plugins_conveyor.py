import json
import os
import time
from pathlib import Path

import yaml

from crapssim_control.plugins.registry import PluginRegistry
from crapssim_control.plugins.loader import PluginLoader, SandboxPolicy
from crapssim_control.plugins.runtime import (
    VerbRegistry,
    PolicyRegistry,
    load_plugins_for_spec,
    write_plugins_manifest,
    clear_registries,
)


def _make_plugin(root: Path, pkg: str, delta: int, ver: str = "1.0.0"):
    plugdir = root / "plugins" / pkg
    (plugdir / "sample").mkdir(parents=True, exist_ok=True)
    code = (
        "class RollStrategy:\n"
        f"    def apply(self, s, p=None): return {{'ok': True, 'delta': {delta}}}\n"
    )
    mod = plugdir / "sample" / "roll_strategy.py"
    mod.write_text(code, encoding="utf-8")
    manifest = {
        "name": pkg,
        "version": "0.1.0",
        "capabilities": [
            {
                "kind": "verb",
                "name": "roll_strategy",
                "version": ver,
                "entry": f"{mod}:RollStrategy",
            }
        ],
    }
    manifest_text = (
        f'name: "{pkg}"\n'
        "version: 0.1.0\n"
        "capabilities:\n"
        "  - kind: verb\n"
        "    name: roll_strategy\n"
        f"    version: {ver}\n"
        f'    entry: "{mod}:RollStrategy"\n'
    )
    (plugdir / "plugin.yaml").write_text(manifest_text, encoding="utf-8")
    return plugdir


def test_isolated_registries_between_runs(tmp_path):
    _make_plugin(tmp_path, "author.sample", delta=2)
    reg_a = PluginRegistry()
    reg_a.discover([str(tmp_path / "plugins")])
    loader = PluginLoader(
        SandboxPolicy(["math", "time"], ["os", "sys", "subprocess"], init_timeout=1.0)
    )
    spec = {
        "use_plugins": [
            {
                "capability": "verb.roll_strategy",
                "version": "1.0.0",
                "ref": "author.sample",
            }
        ]
    }
    loaded_a = load_plugins_for_spec(spec, reg_a, loader)
    verb_a = VerbRegistry.get("roll_strategy")
    assert verb_a and verb_a.apply({})["delta"] == 2

    art_a = tmp_path / "artA"
    art_a.mkdir()
    snap_a = write_plugins_manifest(str(art_a), loaded_a)
    assert os.path.isfile(snap_a)
    clear_registries()

    tmp_b = tmp_path / "B"
    tmp_b.mkdir()
    _make_plugin(tmp_b, "author.sample", delta=9)
    reg_b = PluginRegistry()
    reg_b.discover([str(tmp_b / "plugins")])
    loaded_b = load_plugins_for_spec(spec, reg_b, loader)
    verb_b = VerbRegistry.get("roll_strategy")
    assert verb_b and verb_b.apply({})["delta"] == 9

    assert VerbRegistry.get("roll_strategy").apply({})["delta"] == 9
    art_b = tmp_path / "artB"
    art_b.mkdir()
    snap_b = write_plugins_manifest(str(art_b), loaded_b)
    assert os.path.isfile(snap_b)
    clear_registries()


def test_plugins_manifest_written(tmp_path):
    _make_plugin(tmp_path, "author.sample", delta=3)
    reg = PluginRegistry()
    reg.discover([str(tmp_path / "plugins")])
    loader = PluginLoader(SandboxPolicy(["math"], ["os", "sys"], init_timeout=1.0))
    spec = {
        "use_plugins": [
            {
                "capability": "verb.roll_strategy",
                "version": "1.0.0",
                "ref": "author.sample",
            }
        ]
    }
    loaded = load_plugins_for_spec(spec, reg, loader)
    art = tmp_path / "artifacts"
    art.mkdir()
    outp = write_plugins_manifest(str(art), loaded)
    payload = json.loads(Path(outp).read_text("utf-8"))
    assert "plugins_loaded" in payload and isinstance(payload["plugins_loaded"], list)
