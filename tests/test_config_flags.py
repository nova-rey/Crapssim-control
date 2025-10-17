import pytest

from crapssim_control.config import (
    DEMO_FALLBACKS_DEFAULT,
    coerce_flag,
    normalize_demo_fallbacks,
)


@pytest.mark.parametrize(
    "value, default, expected, ok",
    [
        (True, None, True, True),
        (False, None, False, True),
        (None, True, True, True),
        (None, False, False, True),
        (" true ", None, True, True),
        ("OFF", None, False, True),
        ("DEFAULT", True, True, True),
        (1, None, True, True),
        (0, None, False, True),
        ("maybe", None, None, False),
        (2, None, None, False),
        (object(), None, None, False),
    ],
)
def test_coerce_flag(value, default, expected, ok):
    normalized, success = coerce_flag(value, default=default)
    assert success is ok
    assert normalized == expected


@pytest.mark.parametrize(
    "run_block, expected",
    [
        (None, DEMO_FALLBACKS_DEFAULT),
        ({}, DEMO_FALLBACKS_DEFAULT),
        ({"demo_fallbacks": True}, True),
        ({"demo_fallbacks": "yes"}, True),
        ({"demo_fallbacks": "no"}, False),
        ({"demo_fallbacks": "auto"}, DEMO_FALLBACKS_DEFAULT),
        ({"demo_fallbacks": "unknown"}, DEMO_FALLBACKS_DEFAULT),
    ],
)
def test_normalize_demo_fallbacks(run_block, expected):
    assert normalize_demo_fallbacks(run_block) is expected
