import importlib


def test_capabilities_supported_flags():
    caps = importlib.import_module("crapssim_control.capabilities").get_capabilities()
    assert caps["capabilities_schema"] == "1.0"
    # Truthfulness for vanilla: buy/lay not natively supported
    assert caps["supported"]["buy_bet"] is False
    assert caps["supported"]["lay_bet"] is False
    # ATS advertised
    assert caps["supported"]["ats_all_bet"] is True
    assert caps["supported"]["ats_small_bet"] is True
    assert caps["supported"]["ats_tall_bet"] is True
