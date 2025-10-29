from crapssim_control import __version__
from crapssim_control.controller import JOURNAL_SCHEMA_VERSION, SUMMARY_SCHEMA_VERSION


def test_schema_versions_frozen():
    assert JOURNAL_SCHEMA_VERSION == "1.1"
    assert SUMMARY_SCHEMA_VERSION == "1.1"
    assert __version__.startswith("1.0.")
