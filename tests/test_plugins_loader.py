import io
import os
import tempfile
import textwrap
import time
import pytest
from crapssim_control.plugins.registry import PluginSpec, Capability
from crapssim_control.plugins.loader import PluginLoader, SandboxPolicy


def make_toy_plugin(tmp_path, code):
    f = tmp_path / "toy.py"
    f.write_text(code)
    spec = PluginSpec(
        name="author.safe",
        version="1.0.0",
        capabilities=[Capability(kind="verb", name="toy", version="1.0.0", entry=str(f))],
    )
    return spec


def test_safe_plugin_loads(tmp_path):
    code = "class RollStrategy:\n    def apply(self, s, p=None): return {'ok': True}"
    spec = make_toy_plugin(tmp_path, code)
    loader = PluginLoader(SandboxPolicy(["math"], ["os", "subprocess"], init_timeout=1))
    module = loader.load(spec)
    assert hasattr(module, "RollStrategy")
    rs = module.RollStrategy()
    assert rs.apply({})["ok"]


def test_denied_import_raises(tmp_path):
    code = "import os\nclass X: pass"
    spec = make_toy_plugin(tmp_path, code)
    loader = PluginLoader(SandboxPolicy(["math"], ["os", "sys"], init_timeout=1))
    with pytest.raises(ImportError):
        loader.load(spec)


def test_denied_builtin_raises(tmp_path):
    code = "open('x.txt','w')"
    spec = make_toy_plugin(tmp_path, code)
    loader = PluginLoader(SandboxPolicy(["math"], ["os"], init_timeout=1))
    with pytest.raises(PermissionError):
        loader.load(spec)


def test_timeout_plugin(tmp_path):
    code = "import time\ntime.sleep(2)"
    spec = make_toy_plugin(tmp_path, code)
    loader = PluginLoader(SandboxPolicy(["time"], ["os"], init_timeout=0.2))
    with pytest.raises(TimeoutError):
        loader.load(spec)


def test_namespace_unique(tmp_path):
    code = "x = 1"
    spec = make_toy_plugin(tmp_path, code)
    loader = PluginLoader(SandboxPolicy(["math"], ["os"], init_timeout=1))
    m1 = loader.load(spec)
    time.sleep(0.01)
    m2 = loader.load(spec)
    assert m1 is not m2
    assert m1.__name__ != m2.__name__
