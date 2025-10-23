import textwrap

from crapssim_control.plugins.registry import Capability, PluginRegistry


def make_manifest(tmpdir, name="author.sample", version="0.1.0"):
    plugin_dir = tmpdir / "pluginA"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = f"""
    name: {name}
    version: {version}
    capabilities:
      - kind: verb
        name: roll_strategy
        version: "1.0.0"
        entry: mod:Class
    requires:
      csc_core: ">=0.43,<0.50"
    description: Test plugin
    """
    with open(plugin_dir / "plugin.yaml", "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(manifest).strip() + "\n")
    return plugin_dir


def test_valid_manifest_parses(tmp_path):
    reg = PluginRegistry()
    make_manifest(tmp_path)
    found = reg.discover([str(tmp_path)])
    assert len(found) == 1
    spec = found[0]
    assert spec.name == "author.sample"
    assert spec.version == "0.1.0"
    assert spec.capabilities[0].name == "roll_strategy"


def test_invalid_manifest_missing_keys(tmp_path):
    reg = PluginRegistry()
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    with open(bad_dir / "plugin.yaml", "w", encoding="utf-8") as f:
        f.write("name: x\nversion: 1.0.0\n")
    try:
        reg.discover([str(tmp_path)])
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_semver_parsing(tmp_path):
    reg = PluginRegistry()
    good = make_manifest(tmp_path, version="1.2.3")
    bad = make_manifest(tmp_path / "bad", version="1.2")
    reg.discover([str(good)])
    try:
        reg.discover([str(bad)])
        assert False, "Bad semver should fail"
    except ValueError:
        pass


def test_duplicate_registration(tmp_path):
    reg = PluginRegistry()
    d1 = make_manifest(tmp_path, name="author.one", version="1.0.0")
    d2 = make_manifest(tmp_path / "dup", name="author.one", version="1.0.0")
    reg.discover([str(d1)])
    reg.discover([str(d2)])
    specs = reg.all_specs()
    assert len(specs) == 1


def test_resolve(tmp_path):
    reg = PluginRegistry()
    make_manifest(tmp_path)
    reg.discover([str(tmp_path)])
    spec = reg.resolve("verb", "roll_strategy", "1.0.0")
    assert spec is not None
    assert spec.name == "author.sample"
