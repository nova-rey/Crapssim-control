from crapssim_control.integrations import webhooks


def test_webhook_retry_attempts(monkeypatch):
    attempts = []
    sleeps = []
    warnings = []

    def fake_post(url, headers, data, timeout):
        attempts.append((url, data, timeout))
        raise RuntimeError("boom")

    def fake_sleep(delay):
        sleeps.append(delay)

    def fake_uniform(_a, _b):
        return 0.0

    def fake_warning(msg, *args):
        warnings.append((msg, args))

    monkeypatch.setattr(webhooks, "requests", type("Req", (), {"post": staticmethod(fake_post)}))
    monkeypatch.setattr(webhooks.time, "sleep", fake_sleep)
    monkeypatch.setattr(webhooks.random, "uniform", fake_uniform)
    monkeypatch.setattr(webhooks.log, "warning", fake_warning)

    publisher = webhooks.WebhookPublisher(
        targets=["http://example.test"], enabled=True, timeout=0.1
    )
    publisher._post("http://example.test", "event.test", "{}")

    assert len(attempts) == 3  # initial attempt + 2 retries
    assert len(sleeps) == 2
    assert warnings and "failed" in warnings[0][0]
