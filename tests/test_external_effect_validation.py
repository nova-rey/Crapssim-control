from crapssim_control.engine_adapter import VanillaAdapter, validate_effect_summary


def test_external_path_validates_effect_summary(monkeypatch):
    class DummyController:
        pass

    controller = DummyController()
    controller.adapter = VanillaAdapter()
    controller.adapter.start_session({"seed": 1})

    controller.adapter.apply_action(
        "press",
        {"target": {"bet": "6"}, "amount": {"mode": "dollars", "value": 6}},
    )
    effect = controller.adapter.last_effect

    validate_effect_summary(effect, "1.0")
