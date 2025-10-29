from pathlib import Path

from crapssim_control.plugins.registry import PluginRegistry
from crapssim_control.plugins.loader import PluginLoader, SandboxPolicy
from crapssim_control.plugins.runtime import VerbRegistry, load_plugins_for_spec


def _write_plugin(
    tmp_path: Path, name="author.sample", cap_kind="verb", cap_name="roll_strategy", cap_ver="1.0.0"
):
    root = tmp_path / "plugins" / "author.sample"
    (root / "sample").mkdir(parents=True, exist_ok=True)
    (root / "sample" / "roll_strategy.py").write_text(
        "from typing import Any, Dict\n"
        "class RollStrategy:\n"
        "    def apply(self, state: Dict[str, Any], params=None):\n"
        "        return {'ok': True, 'delta': 2}\n",
        encoding="utf-8",
    )
    entry_path = root / "sample/roll_strategy.py"
    manifest_yaml = (
        f"name: {name}\n"
        "version: 0.1.0\n"
        "capabilities:\n"
        f"  - kind: {cap_kind}\n"
        f"    name: {cap_name}\n"
        f"    version: {cap_ver}\n"
        f"    entry: {entry_path}:RollStrategy\n"
        "requires:\n"
        '  csc_core: ">=0.43,<0.50"\n'
        "description: test plugin\n"
    )
    with open(root / "plugin.yaml", "w", encoding="utf-8") as f:
        f.write(manifest_yaml)
    return root


def test_load_and_register_verb(tmp_path):
    _write_plugin(tmp_path)
    reg = PluginRegistry()
    reg.discover([str(tmp_path / "plugins")])
    loader = PluginLoader(
        SandboxPolicy(["math", "time", "typing"], ["os", "sys", "subprocess"], init_timeout=1.0)
    )
    spec_dict = {
        "use_plugins": [
            {"capability": "verb.roll_strategy", "version": "1.0.0", "ref": "author.sample"}
        ]
    }
    loaded = load_plugins_for_spec(spec_dict, reg, loader)
    assert any(x.get("status") == "ok" for x in loaded)
    # Registered verb available
    v = VerbRegistry.get("roll_strategy")
    assert v is not None
    out = v.apply({"bankroll": 1000})
    assert out.get("ok") is True
    assert out.get("delta") == 2


def test_missing_plugin_yields_trace(tmp_path):
    reg = PluginRegistry()
    loader = PluginLoader(SandboxPolicy(["math"], ["os", "sys"], init_timeout=1.0))
    spec_dict = {
        "use_plugins": [
            {"capability": "verb.roll_strategy", "version": "1.0.0", "ref": "no.such.plugin"}
        ]
    }
    loaded = load_plugins_for_spec(spec_dict, reg, loader)
    assert loaded and loaded[0]["status"] == "missing"


def test_loader_denies_os_even_via_runtime(tmp_path):
    # naughty plugin tries to import os
    root = tmp_path / "plugins" / "author.bad"
    (root).mkdir(parents=True, exist_ok=True)
    p = root / "naughty.py"
    p.write_text(
        "import os\nclass RollStrategy:\n    def apply(self,s,p=None): return {'ok':True}\n",
        encoding="utf-8",
    )
    manifest_yaml = (
        "name: author.bad\n"
        "version: 0.0.1\n"
        "capabilities:\n"
        f"  - kind: verb\n"
        f"    name: roll_strategy\n"
        f"    version: 1.0.0\n"
        f"    entry: {p}:RollStrategy\n"
    )
    with open(root / "plugin.yaml", "w", encoding="utf-8") as f:
        f.write(manifest_yaml)
    reg = PluginRegistry()
    reg.discover([str(tmp_path / "plugins")])
    loader = PluginLoader(SandboxPolicy(["math"], ["os", "sys", "subprocess"], init_timeout=1.0))
    spec_dict = {
        "use_plugins": [
            {"capability": "verb.roll_strategy", "version": "1.0.0", "ref": "author.bad"}
        ]
    }
    loaded = load_plugins_for_spec(spec_dict, reg, loader)
    assert loaded[0]["status"] == "load_error"
