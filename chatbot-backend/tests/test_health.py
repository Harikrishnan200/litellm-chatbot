from tests.conftest import HEADERS


async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_invalid_request_is_rejected(client):
    response = await client.post("/chat", json={"message": ""}, headers=HEADERS)
    assert response.status_code == 422


async def test_missing_api_key_is_rejected(client):
    response = await client.post("/chat", json={"message": "hi"})
    assert response.status_code == 401


async def test_wrong_api_key_is_rejected(client):
    response = await client.post("/chat", json={"message": "hi"}, headers={"X-API-Key": "nope"})
    assert response.status_code == 401


async def test_metrics_endpoint(client):
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "llm_requests_total" in response.text


async def test_oversized_request_is_rejected(client):
    big = {"message": "a" * 20_000}
    response = await client.post("/chat", json=big, headers=HEADERS)
    assert response.status_code == 413
