from crapssim_control.external.http_api import _validate_and_attach_effect
from crapssim_control.engine_adapter import VanillaAdapter


def test_validate_and_attach_effect_sets_field(monkeypatch):
    class C:
        pass

    c = C()
    c.adapter = VanillaAdapter()
    c.adapter.apply_action(
        "press",
        {"target": {"bet": "6"}, "amount": {"mode": "dollars", "value": 6}},
    )
    entry = {}
    _validate_and_attach_effect(c, entry)
    assert "effect_summary" in entry
    assert entry["effect_summary"]["verb"] == "press"
