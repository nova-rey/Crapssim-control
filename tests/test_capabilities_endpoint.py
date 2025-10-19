from crapssim_control.external.http_api import get_capabilities


def test_capabilities_lists_verbs_policies_and_schema():
    caps = get_capabilities()
    assert caps["schema_versions"]["effect"] == "1.0"
    assert "press" in caps["verbs"]
    assert "apply_policy" in caps["verbs"]
    assert "martingale_v1" in caps["policies"]
