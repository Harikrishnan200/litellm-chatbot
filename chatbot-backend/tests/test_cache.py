from app import cache
from tests.conftest import HEADERS, answer_text, fake_open_stream, parse_sse


async def test_cache_hit_avoids_llm_call(client, monkeypatch):
    fake = fake_open_stream(["Hello ", "world"])
    monkeypatch.setattr("app.streaming.open_stream", fake)

    first = await client.post("/chat", json={"message": "Say hello"}, headers=HEADERS)
    second = await client.post("/chat", json={"message": "  say   HELLO "}, headers=HEADERS)  # same after normalizing

    assert len(fake.calls) == 1  # the second request never reached LiteLLM
    events = parse_sse(second.text)
    assert answer_text(events) == "Hello world"
    assert events[-1]["cached"] is True
    assert parse_sse(first.text)[-1]["cached"] is False


def test_cache_key_ignores_case_and_spaces():
    assert cache.make_cache_key("Hi  there") == cache.make_cache_key("hi there")


async def test_stream_sends_meta_and_done_stats(client, monkeypatch):
    monkeypatch.setattr("app.streaming.open_stream", fake_open_stream(["Hi"]))
    events = parse_sse((await client.post("/chat", json={"message": "stats?"}, headers=HEADERS)).text)
    assert events[0]["type"] == "meta" and events[0]["model"] == "test/model" and events[0]["attempts"] == 1
    assert {"latency", "prompt_tokens", "completion_tokens", "cost"} <= events[-1].keys()
