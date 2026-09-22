"""Contract tests for Sprint 0 / T-01: /v1 aliases, structured errors, request IDs."""

import httpx
import pytest


@pytest.fixture
async def client():
    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health_contract(client):
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert "version" in body
    assert "x-request-id" in {k.lower(): v for k, v in r.headers.items()}


async def test_v1_alias_and_legacy_deprecation(client):
    v1 = await client.get("/v1/health")
    assert v1.status_code == 200
    legacy = await client.get("/health")
    assert legacy.headers.get("deprecation") == "true"
    assert "sunset" in {k.lower() for k in legacy.headers}
    assert "/v1/health" in legacy.headers.get("link", "")


async def test_structured_404(client):
    r = await client.get("/no-such-route")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert body["request_id"]


async def test_validation_error_is_400_structured(client):
    r = await client.post("/predict", json={})
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]
    assert body["request_id"]


async def test_model_unavailable_structured(client):
    from models.flood_model import get_model

    if get_model().is_trained:
        pytest.skip("a trained model artefact exists in this environment")
    r = await client.post("/predict", json={"latitude": 19.07, "longitude": 72.87})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "model_unavailable"


async def test_request_id_echoed(client):
    r = await client.get("/health", headers={"X-Request-ID": "req_test_123"})
    assert r.headers["x-request-id"] == "req_test_123"
