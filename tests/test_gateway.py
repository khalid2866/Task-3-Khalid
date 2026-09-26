"""Stage 2 tests — gateway resilience (mocked transport)."""
import requests

from studio import gateway
from studio.exceptions import InferenceFailure, NetworkFailure, StudioError


class FakeResponse:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text


def test_connect_timeout_fails_fast_no_retry(monkeypatch):
    calls = []

    def fake_post(*a, **k):
        calls.append(1)
        raise requests.exceptions.ConnectTimeout("nope")

    monkeypatch.setattr(requests, "post", fake_post)
    try:
        gateway.resilient_post("http://x", json={}, max_attempts=5)
        assert False, "should have raised"
    except NetworkFailure:
        pass
    assert len(calls) == 1, "ConnectTimeout must fail fast with zero retries"


def test_read_timeout_retries_then_succeeds(monkeypatch):
    calls = []

    def fake_post(*a, **k):
        calls.append(1)
        if len(calls) < 3:
            raise requests.exceptions.ReadTimeout("slow")
        return FakeResponse(200)

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(gateway.time, "sleep", lambda s: None)
    resp = gateway.resilient_post("http://x", json={}, max_attempts=5)
    assert resp.status_code == 200
    assert len(calls) == 3


def test_429_retries_400_raises_immediately(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(429))
    monkeypatch.setattr(gateway.time, "sleep", lambda s: None)
    try:
        gateway.resilient_post("http://x", json={}, max_attempts=3)
        assert False, "should have raised"
    except InferenceFailure:
        pass

    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(400, "bad"))
    try:
        gateway.resilient_post("http://x", json={}, max_attempts=3)
        assert False, "should have raised"
    except StudioError as exc:
        assert "400" in str(exc)


def test_backoff_grows_with_jitter():
    d1 = gateway._backoff_delay(1)
    d4 = gateway._backoff_delay(4)
    assert 2.0 <= d1 <= 3.0
    assert 16.0 <= d4 <= 17.0
    assert d4 > d1
