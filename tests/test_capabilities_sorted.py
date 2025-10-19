from crapssim_control.external.http_api import get_capabilities


def test_capabilities_sorted_and_schema_versions_present():
    caps = get_capabilities()
    assert "schema_versions" in caps
    assert caps["schema_versions"]["effect"] == "1.0"
    verbs = caps["verbs"]
    assert verbs == sorted(verbs)
