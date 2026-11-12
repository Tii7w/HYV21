import httpx
import pytest

from app.network.client import AccessDeniedError, BlockedHostError, NetworkClient, NetworkError, RateLimitedError
from app.network.rate_limiter import RateLimitConfig, SourceRateLimiter, TokenBucket


def make_client(responses, max_retries=2):
    calls, failures, sleeps = [], [], []

    def handler(request):
        calls.append(request)
        result = responses[min(len(calls) - 1, len(responses) - 1)]
        if isinstance(result, Exception):
            raise result
        return result

    limiter = SourceRateLimiter(RateLimitConfig(per_minute=600, per_hour=6000, max_concurrency=1, min_interval_ms=0))
    client = NetworkClient(
        "authorized", limiter, max_retries=max_retries, transport=httpx.MockTransport(handler),
        on_failure=lambda url, code, error, attempts: failures.append((url, code, attempts)), sleep=sleeps.append,
    )
    return client, calls, failures, sleeps


def test_403_is_never_retried():
    client, calls, failures, _ = make_client([httpx.Response(403)])
    with pytest.raises(AccessDeniedError):
        client.get_json("https://feed.example.com/items?api_key=SECRET")
    assert len(calls) == 1
    assert failures == [("https://feed.example.com/items", 403, 1)]  # Sorgu (anahtar) DLQ'ya yazılmaz.


def test_429_honours_retry_after_once():
    client, calls, _, sleeps = make_client([httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, json={"items": []})])
    assert client.get_json("https://feed.example.com/items") == {"items": []}
    assert sleeps == [7.0] and len(calls) == 2


def test_429_without_retry_after_stops():
    client, calls, failures, _ = make_client([httpx.Response(429)])
    with pytest.raises(RateLimitedError):
        client.get_json("https://feed.example.com/items")
    assert len(calls) == 1 and failures[0][1] == 429


def test_repeated_429_stops_after_one_wait():
    client, calls, _, _ = make_client([httpx.Response(429, headers={"Retry-After": "1"})])
    with pytest.raises(RateLimitedError):
        client.get_json("https://feed.example.com/items")
    assert len(calls) == 2


def test_5xx_limited_retries_then_dead_letter():
    client, calls, failures, sleeps = make_client([httpx.Response(503)], max_retries=2)
    with pytest.raises(NetworkError):
        client.get_json("https://feed.example.com/items")
    assert len(calls) == 3 and len(sleeps) == 2 and sleeps[1] >= sleeps[0] / 2
    assert failures == [("https://feed.example.com/items", 503, 3)]


def test_timeout_retried():
    client, calls, _, _ = make_client([httpx.ReadTimeout("t"), httpx.Response(200, json={"ok": 1})])
    assert client.get_json("https://feed.example.com/items") == {"ok": 1}
    assert len(calls) == 2


def test_sahibinden_pages_blocked_without_official_api():
    client, calls, _, _ = make_client([httpx.Response(200, json={})])
    with pytest.raises(BlockedHostError):
        client.get_json("https://www.sahibinden.com/satilik-daire")
    assert calls == []


def test_token_bucket():
    now = [0.0]
    bucket = TokenBucket(2, 60.0, clock=lambda: now[0])
    assert bucket.try_consume() and bucket.try_consume() and not bucket.try_consume()
    now[0] = 30.0
    assert bucket.try_consume()
