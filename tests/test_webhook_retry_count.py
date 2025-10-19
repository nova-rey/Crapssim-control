from types import SimpleNamespace

from crapssim_control.integrations import webhooks


def test_webhook_retry_count(monkeypatch):
    publisher = webhooks.WebhookPublisher(targets=["http://example.com"], enabled=True, timeout=0.1)
    attempts = {"count": 0}

    def fake_post(url, headers, data, timeout):  # noqa: ARG001
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("boom")
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(webhooks.requests, "post", fake_post)
    monkeypatch.setattr(webhooks.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(webhooks.random, "uniform", lambda *_args, **_kwargs: 0.0)

    publisher._post("http://example.com", "test-event", "{}")

    assert attempts["count"] == 3
