"""Short-term, per-session conversation memory stored in Redis.

Only completed user/assistant exchanges are saved. Redis expiry keeps the
feature bounded and a rolling window keeps prompts within a predictable size.
Memory is best-effort: a Redis outage must never stop a chat request.
"""
import json
import logging

import redis.asyncio as redis

from app import config

log = logging.getLogger("smartroute")
redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)


def memory_key(session_id: str) -> str:
    return f"memory:{session_id}"


async def get_history(session_id: str | None) -> list[dict]:
    """Return the saved OpenAI-format messages for a browser session."""
    if not config.MEMORY_ENABLED or not session_id:
        return []
    try:
        values = await redis_client.lrange(memory_key(session_id), 0, -1)
        # Refresh the sliding expiry whenever someone returns to a conversation.
        if values:
            await redis_client.expire(memory_key(session_id), config.MEMORY_TTL)
    except redis.RedisError:
        log.warning("memory lookup failed, continuing without conversation history")
        return []

    history = []
    for value in values:
        try:
            message = json.loads(value)
        except json.JSONDecodeError:
            continue
        if message.get("role") in {"user", "assistant"} and isinstance(message.get("content"), str):
            history.append(message)
    return history


async def save_turn(session_id: str | None, user_message: str, assistant_message: str) -> None:
    """Append one completed exchange, keeping only the configured recent turns."""
    if not config.MEMORY_ENABLED or not session_id or not assistant_message:
        return
    key = memory_key(session_id)
    encoded = [
        json.dumps({"role": "user", "content": user_message}),
        json.dumps({"role": "assistant", "content": assistant_message}),
    ]
    try:
        pipeline = redis_client.pipeline()
        pipeline.rpush(key, *encoded)
        pipeline.ltrim(key, -2 * config.MEMORY_MAX_TURNS, -1)
        pipeline.expire(key, config.MEMORY_TTL)
        await pipeline.execute()
    except redis.RedisError:
        log.warning("memory write failed")
