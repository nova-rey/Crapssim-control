import importlib.util
import sys
import threading
import time
from dataclasses import dataclass
from typing import List
from types import ModuleType
import builtins
from .registry import PluginSpec


@dataclass
class SandboxPolicy:
    allowed_modules: List[str]
    deny_modules: List[str]
    init_timeout: float = 1.0


class PluginLoader:
    """Loads plugin modules with a lightweight sandbox."""

    def __init__(self, policy: SandboxPolicy):
        self.policy = policy

    def _sandbox_builtins(self) -> dict:
        safe_builtins = {}
        builtin_module = builtins
        restricted = {"open", "exec", "eval", "compile"}

        for name in dir(builtin_module):
            if name in restricted:
                continue
            safe_builtins[name] = getattr(builtin_module, name)

        def denied(*_, **__):
            raise PermissionError("Access to restricted builtin denied.")

        for name in restricted:
            safe_builtins[name] = denied

        allowed = set(self.policy.allowed_modules)
        denied_modules = set(self.policy.deny_modules)

        def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
            target_name = name
            if level != 0 and globals is not None and "__package__" in globals:
                # Delegate resolution of relative imports to the real importer after checks
                pass

            root = target_name.split(".", 1)[0]
            if any(root == dm or root.startswith(f"{dm}.") for dm in denied_modules):
                raise ImportError(f"Import of '{name}' denied by sandbox policy")

            if allowed and root not in allowed:
                raise ImportError(f"Import of '{name}' not allowed by sandbox policy")

            module = builtin_module.__import__(name, globals, locals, fromlist, level)
            # After import, ensure that full module path is not denied
            full_name = module.__name__
            if any(
                full_name == dm or full_name.startswith(f"{dm}.")
                for dm in denied_modules
            ):
                raise ImportError(f"Import of '{full_name}' denied by sandbox policy")
            return module

        safe_builtins["__import__"] = safe_import
        return safe_builtins

    def _deny_import_hook(self):
        """Simple meta_path hook blocking disallowed modules."""
        policy = self.policy

        class DenyImporter:
            def find_spec(self, fullname, path, target=None):
                for mod in policy.deny_modules:
                    if fullname == mod or fullname.startswith(mod + "."):
                        raise ImportError(
                            f"Import of '{fullname}' denied by sandbox policy"
                        )
                return None

        return DenyImporter()

    def load(self, plugin_spec: PluginSpec) -> ModuleType:
        """Import the module declared in the plugin manifest entry path."""
        if not plugin_spec.capabilities:
            raise ValueError("No capabilities found in plugin spec")

        entry = plugin_spec.capabilities[0].entry
        mod_path = entry.partition(":")[0]
        plugin_name = plugin_spec.name.replace(".", "_")
        unique_name = f"plugins.{plugin_name}_{int(time.time()*1000)}"

        deny_hook = self._deny_import_hook()
        sys.meta_path.insert(0, deny_hook)
        sys_modules_before = set(sys.modules.keys())
        sandbox_builtins = self._sandbox_builtins()

        result: dict = {}

        def _do_import():
            try:
                spec = importlib.util.spec_from_file_location(unique_name, mod_path)
                if spec is None:
                    raise ImportError(f"Cannot locate {mod_path}")
                module = importlib.util.module_from_spec(spec)
                module.__builtins__ = sandbox_builtins
                sys.modules[unique_name] = module
                loader = spec.loader
                if loader is None:
                    raise ImportError(f"No loader for {mod_path}")
                loader.exec_module(module)
                result["module"] = module
            except Exception as exc:  # pragma: no cover - captured for tests
                result["error"] = exc

        thread = threading.Thread(target=_do_import, daemon=True)
        thread.start()
        thread.join(timeout=self.policy.init_timeout)

        if thread.is_alive():
            sys.meta_path.remove(deny_hook)
            for name in list(sys.modules.keys()):
                if name not in sys_modules_before and name.startswith("plugins."):
                    sys.modules.pop(name, None)
            raise TimeoutError(f"Plugin '{plugin_spec.name}' init exceeded timeout")

        sys.meta_path.remove(deny_hook)

        for name in list(sys.modules.keys()):
            if name not in sys_modules_before and name.startswith("plugins."):
                if "module" not in result or sys.modules[name] is not result.get("module"):
                    sys.modules.pop(name, None)

        if "error" in result:
            raise result["error"]

        return result["module"]
