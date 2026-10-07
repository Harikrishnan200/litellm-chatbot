"""A prompt rejected by LiteLLM's guardrail must show as "blocked", not as a provider outage."""
import httpx
from openai import BadRequestError

from tests.conftest import HEADERS, parse_sse


async def test_guardrail_block_is_reported_as_blocked(client, monkeypatch):
    async def open_stream(model, messages, request_id):
        response = httpx.Response(400, request=httpx.Request("POST", "http://litellm"))
        body = {"message": "Content blocked: us_ssn pattern detected",
                "provider_specific_fields": {"pattern": "us_ssn"}}
        raise BadRequestError("Content blocked: us_ssn pattern detected", response=response, body=body)

    monkeypatch.setattr("app.streaming.open_stream", open_stream)
    response = await client.post("/chat", json={"message": "my ssn is 123-45-6789"}, headers=HEADERS)

    last = parse_sse(response.text)[-1]
    assert last["type"] == "blocked"
    assert last["reason"] == "us_ssn"
