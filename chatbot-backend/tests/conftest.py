"""Shared test setup: fake Redis, fake LiteLLM stream, and an HTTP client for the app."""
import json
from types import SimpleNamespace

import fakeredis.aioredis
import httpx
import pytest

from app import cache, config, rate_limit
from app.main import app

HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture(autouse=True)
def fake_env(monkeypatch):
    """Every test gets an empty in-memory Redis and known settings. No real network."""
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache, "redis_client", fake_redis)
    monkeypatch.setattr(rate_limit, "redis_client", fake_redis)
    monkeypatch.setattr(config, "API_KEY", "test-key")
    monkeypatch.setattr(config, "CACHE_ENABLED", True)
    monkeypatch.setattr(config, "RATE_LIMIT_REQUESTS", 100)


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def make_chunk(text: str):
    """Looks like an OpenAI stream chunk: chunk.choices[0].delta.content"""
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


def fake_open_stream(pieces: list[str], fail_after_pieces: bool = False, deployment: str = "coding-openrouter"):
    """Build a replacement for chat.open_stream that yields `pieces` (optionally then crashes)."""
    calls = []

    async def open_stream(model, messages, request_id):
        calls.append({"model": model, "messages": messages})
        route, _, provider = deployment.partition("-")
        info = {"route": route, "provider": provider, "model": "test/model", "tier": "", "score": "", "retries": 0, "fallbacks": 0}

        async def stream():
            for piece in pieces:
                yield make_chunk(piece)
            if fail_after_pieces:
                raise ConnectionError("provider died")

        return info, stream()

    open_stream.calls = calls
    return open_stream


def parse_sse(body: str) -> list[dict]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


def answer_text(events: list[dict]) -> str:
    return "".join(e["text"] for e in events if e["type"] == "token")
