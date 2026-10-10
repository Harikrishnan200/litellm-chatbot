"""Conversation memory is saved per session and becomes model context on the next turn."""
from tests.conftest import HEADERS, fake_open_stream


async def test_memory_is_restored_and_sent_to_the_model(client, monkeypatch):
    fake = fake_open_stream(["I will remember that."])
    monkeypatch.setattr("app.streaming.open_stream", fake)
    session_id = "browser-session-1"

    first = await client.post(
        "/chat",
        json={"message": "My name is Ada.", "session_id": session_id},
        headers=HEADERS,
    )
    assert first.status_code == 200

    second = await client.post(
        "/chat",
        json={"message": "What is my name?", "session_id": session_id},
        headers=HEADERS,
    )
    assert second.status_code == 200
    assert [message["role"] for message in fake.calls[1]["messages"]] == [
        "system", "user", "assistant", "user",
    ]
    assert fake.calls[1]["messages"][1]["content"] == "My name is Ada."
    assert fake.calls[1]["messages"][2]["content"] == "I will remember that."

    history = await client.get(f"/chat/history?session_id={session_id}", headers=HEADERS)
    assert history.status_code == 200
    assert [message["content"] for message in history.json()["messages"]] == [
        "My name is Ada.", "I will remember that.",
        "What is my name?", "I will remember that.",
    ]
