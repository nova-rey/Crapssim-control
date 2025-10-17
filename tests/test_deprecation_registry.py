import importlib
import sys
import warnings

import pytest


@pytest.fixture(autouse=True)
def _reset_deprecations():
    import crapssim_control.deprecations as deprecations

    importlib.reload(deprecations)
    yield


def test_warn_once_emits_single_warning():
    import crapssim_control.deprecations as deprecations

    module = importlib.reload(deprecations)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        module.warn_once("test-key", "deprecated message")
        module.warn_once("test-key", "deprecated message")

    dep_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(dep_warnings) == 1


def _import_and_reload(module_name: str):
    sys.modules.pop(module_name, None)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        module = importlib.import_module(module_name)
        importlib.reload(module)

    return [w for w in caught if issubclass(w.category, DeprecationWarning)]


def test_shim_imports_warn_once_each():
    warnings_per_module = []

    for name in ("templates_rt", "rules_rt", "legalize_rt"):
        module_name = f"crapssim_control.{name}"
        warnings_per_module.append(_import_and_reload(module_name))

    for warning_list in warnings_per_module:
        assert len(warning_list) == 1


def test_canonical_imports_emit_no_deprecation_warnings():
    for name in ("templates", "rules_engine", "legalize"):
        module_name = f"crapssim_control.{name}"
        warnings_for_module = _import_and_reload(module_name)
        assert not warnings_for_module
