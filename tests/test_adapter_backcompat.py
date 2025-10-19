from crapssim_control.engine_adapter import NullAdapter


def test_null_adapter_attach_and_play_exist_and_return_shapes():
    a = NullAdapter()
    res_attach = a.attach({})
    assert isinstance(res_attach, dict) and res_attach.get("attached") is True
    res_play = a.play(shooters=1, rolls=2)
    assert isinstance(res_play, dict)
    assert res_play.get("status") in ("noop", "ok")


def test_null_adapter_attach_cls_returns_truthy():
    res = NullAdapter.attach_cls({})
    assert isinstance(res, dict) and res.get("attached") is True
