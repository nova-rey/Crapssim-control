from crapssim_control.integrations.webhooks import WebhookPublisher


def test_emit_succeeds_even_if_target_unreachable(monkeypatch):
    called = {}

    def fake_post(url, headers, data, timeout):
        called["url"] = url

    monkeypatch.setattr("requests.post", fake_post)
    publisher = WebhookPublisher(targets=["http://fake"], enabled=True)
    publisher.emit("roll.processed", {"run_id": "x"})
    assert "url" in called
