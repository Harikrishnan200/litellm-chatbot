"""Mid-stream recovery and the graceful 'everything failed' path."""
from app import config
from tests.conftest import HEADERS, make_chunk, parse_sse


async def test_midstream_failure_continues_with_recovery_model(client, monkeypatch):
    calls = []

    async def open_stream(model, messages, request_id):
        calls.append({"model": model, "messages": messages})
        info = {"route": "coding", "provider": "openrouter", "model": "test/model", "tier": "", "score": "", "retries": 0, "fallbacks": 0}

        async def primary():
            yield make_chunk("Kubernetes is ")
            yield make_chunk("an open-source ")
            raise ConnectionError("provider died")

        async def recovery():
            yield make_chunk("container orchestrator.")

        return info, (primary() if model == config.ROUTER_MODEL else recovery())

    monkeypatch.setattr("app.streaming.open_stream", open_stream)
    response = await client.post("/chat", json={"message": "What is Kubernetes?"}, headers=HEADERS)

    events = parse_sse(response.text)
    answer = "".join(e["text"] for e in events if e["type"] == "token")
    assert answer == "Kubernetes is an open-source container orchestrator."
    assert events[-1]["recovered"] is True
    # the recovery call was made on the recovery model and was given the prefix
    assert calls[1]["model"] == config.RECOVERY_MODEL
    assert "Kubernetes is an open-source " in str(calls[1]["messages"])


async def test_all_providers_failing_returns_graceful_error(client, monkeypatch):
    async def open_stream(model, messages, request_id):
        raise ConnectionError("every provider is down")

    monkeypatch.setattr("app.streaming.open_stream", open_stream)
    response = await client.post("/chat", json={"message": "hello"}, headers=HEADERS)

    assert response.status_code == 200  # the stream itself works; the last event is the error
    events = parse_sse(response.text)
    assert events[-1]["type"] == "error"
    assert "unavailable" in events[-1]["message"]
