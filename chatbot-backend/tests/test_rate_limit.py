from app import config
from tests.conftest import HEADERS, fake_open_stream


async def test_rate_limit_is_enforced(client, monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_REQUESTS", 2)
    monkeypatch.setattr("app.streaming.open_stream", fake_open_stream(["ok"]))

    for i in range(2):
        response = await client.post("/chat", json={"message": f"question {i}"}, headers=HEADERS)
        assert response.status_code == 200

    response = await client.post("/chat", json={"message": "one too many"}, headers=HEADERS)
    assert response.status_code == 429
    assert "Rate limit" in response.json()["detail"]
