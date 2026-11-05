
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

import database
import gateway
import model_router
from rate_limiter import TokenRateLimiter
from model_router import GatewayError


# Each test gets its own SQLite database.
@pytest.fixture
def limiter(tmp_path, monkeypatch):
    monkeypatch.setattr(
        database,
        "DB_PATH",
        tmp_path / "test_rate_limits.db"
    )
    return TokenRateLimiter(limit=50_000, window=60)


# 1. Sliding window and expiration
def test_sliding_window(limiter):
    now = 2_000_000_000.0

    first = limiter.reserve("tenant-a", 20_000, now)
    second = limiter.reserve("tenant-a", 25_000, now + 10)
    third = limiter.reserve("tenant-a", 10_000, now + 20)
    fourth = limiter.reserve("tenant-a", 10_000, now + 61)

    assert first.allowed
    assert second.allowed
    assert not third.allowed
    assert third.retry_after == pytest.approx(40)
    assert fourth.allowed
    assert fourth.used_tokens == 35_000


# 2. Exactly at capacity
def test_exact_limit(limiter):
    result = limiter.reserve("tenant-a", 50_000)

    assert result.allowed
    assert result.remaining_tokens == 0

    rejected = limiter.reserve("tenant-a", 1)

    assert not rejected.allowed


# 3. Tenant isolation
def test_tenant_isolation(limiter):
    assert limiter.reserve("tenant-a", 50_000).allowed
    assert limiter.reserve("tenant-b", 50_000).allowed

    assert not limiter.reserve("tenant-a", 1).allowed
    assert not limiter.reserve("tenant-b", 1).allowed


# 4. Concurrent SQLite reservations
def test_concurrent_requests(limiter):
    now = time.time()

    def make_reservation(_):
        return limiter.reserve(
            "concurrent-tenant",
            10_000,
            now=now
        )

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(make_reservation, range(10)))

    accepted = [r for r in results if r.allowed]
    rejected = [r for r in results if not r.allowed]

    assert len(accepted) == 5
    assert len(rejected) == 5


# 5. Invalid token reservation
def test_invalid_token_amount(limiter):
    with pytest.raises(ValueError):
        limiter.reserve("tenant-a", -100)

    with pytest.raises(ValueError):
        limiter.reserve("tenant-a", 0)

    with pytest.raises(ValueError):
        limiter.reserve("tenant-a", True)


# 6. Primary 429 triggers fallback
def test_primary_429_fallback(monkeypatch):
    calls = []

    async def fake_request(client, url, payload, timeout_seconds):
        calls.append(url)

        if url == model_router.PRIMARY_URL:
            return httpx.Response(429)

        return httpx.Response(
            200,
            json={"completion": "Backup response"}
        )

    monkeypatch.setattr(
        model_router, "request_model", fake_request
    )

    result = asyncio.run(
        model_router.route_completion({"prompt": "Hello"})
    )

    assert result["provider"] == "backup"
    assert len(calls) == 2


# 7. Primary timeout triggers fallback
def test_primary_timeout_fallback(monkeypatch):
    calls = []

    # Shorten deadline only for this automated test.
    monkeypatch.setattr(model_router, "PRIMARY_TIMEOUT", 0.02)

    async def fake_request(client, url, payload, timeout_seconds):
        calls.append(url)

        if url == model_router.PRIMARY_URL:
            async with asyncio.timeout(timeout_seconds):
                await asyncio.sleep(0.1)

        return httpx.Response(
            200,
            json={"completion": "Backup response"}
        )

    monkeypatch.setattr(
        model_router, "request_model", fake_request
    )

    result = asyncio.run(
        model_router.route_completion({"prompt": "Hello"})
    )

    assert result["provider"] == "backup"
    assert len(calls) == 2


# 8. Primary 500 does not trigger fallback
def test_primary_500_sanitized(monkeypatch):
    calls = []

    async def fake_request(client, url, payload, timeout_seconds):
        calls.append(url)
        return httpx.Response(
            500,
            text="Private provider traceback"
        )

    monkeypatch.setattr(
        model_router, "request_model", fake_request
    )

    with pytest.raises(GatewayError) as exc:
        asyncio.run(
            model_router.route_completion({"prompt": "Hello"})
        )

    assert exc.value.code == "UPSTREAM_ERROR"
    assert "Private provider traceback" not in exc.value.message
    assert len(calls) == 1


# 9. Gateway accepts authorized tenant
def test_gateway_success(limiter, monkeypatch):
    monkeypatch.setattr(gateway, "limiter", limiter)

    async def fake_route(payload):
        assert payload["max_tokens"] == 100
        return {
            "provider": "primary",
            "result": {"completion": "Hello!"}
        }

    monkeypatch.setattr(gateway, "route_completion", fake_route)

    client = TestClient(gateway.app)

    response = client.post(
        "/completions",
        headers={"X-API-Key": "demo-key-tenant-a"},
        json={
            "prompt": "Hello",
            "max_tokens": 100
        }
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "primary"
    assert response.json()["usage"]["reserved_tokens"] > 0


# 10. Gateway rejects invalid API key
def test_gateway_authentication():
    client = TestClient(gateway.app)

    response = client.post(
        "/completions",
        headers={"X-API-Key": "invalid-key"},
        json={"prompt": "Hello"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_API_KEY"


# 11. Gateway blocks requests exceeding quota
def test_gateway_rate_limit(limiter, monkeypatch):
    monkeypatch.setattr(gateway, "limiter", limiter)

    called = False

    async def fake_route(payload):
        nonlocal called
        called = True
        return {"provider": "primary", "result": {}}

    monkeypatch.setattr(gateway, "route_completion", fake_route)

    limiter.reserve("tenant-a", 50_000)

    client = TestClient(gateway.app)

    response = client.post(
        "/completions",
        headers={"X-API-Key": "demo-key-tenant-a"},
        json={
            "prompt": "Hello",
            "max_tokens": 100
        }
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert "Retry-After" in response.headers
    assert not called


# 12. Gateway sanitizes upstream errors
def test_gateway_error_sanitization(limiter, monkeypatch):
    monkeypatch.setattr(gateway, "limiter", limiter)

    async def fake_route(payload):
        raise GatewayError(
            "UPSTREAM_ERROR",
            "Primary model provider failed"
        )

    monkeypatch.setattr(gateway, "route_completion", fake_route)

    client = TestClient(gateway.app)

    response = client.post(
        "/completions",
        headers={"X-API-Key": "demo-key-tenant-b"},
        json={"prompt": "Hello"}
    )

    assert response.status_code == 502
    assert response.json()["error"] == {
        "code": "UPSTREAM_ERROR",
        "message": "Primary model provider failed"
    }


def test_validation_errors_use_gateway_payload():
    response = TestClient(gateway.app).post(
        "/completions", headers={"X-API-Key": "demo-key-tenant-a"},
        json={"prompt": "Hello", "max_tokens": True}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_impossible_budget_is_not_retryable(limiter, monkeypatch):
    monkeypatch.setattr(gateway, "limiter", limiter)
    response = TestClient(gateway.app).post(
        "/completions", headers={"X-API-Key": "demo-key-tenant-a"},
        json={"prompt": "Hello", "max_tokens": 50000}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "TOKEN_BUDGET_TOO_LARGE"


def test_non_ascii_token_reservation():
    assert gateway.estimate_tokens("你好", 10) == 16


def test_backup_failure_scenario_reaches_backup():
    from mock_providers import app
    client = TestClient(app)
    payload = {"prompt": "Hello", "scenario": "backup_failure"}
    assert client.post("/primary", json=payload).status_code == 429
    assert client.post("/backup", json=payload).status_code == 503


def test_request_deadline_cancels_inflight_request():
    cancelled = False

    class SlowClient:
        async def post(self, *args, **kwargs):
            nonlocal cancelled
            try:
                await asyncio.sleep(10)
            finally:
                cancelled = True

    with pytest.raises(TimeoutError):
        asyncio.run(model_router.request_model(SlowClient(), "unused", {}, 0.01))
    assert cancelled
