"""Response cache in Redis.

key:   cache:<sha256 of the normalized message and prior conversation>
value: JSON {"text": ..., "provider": ..., "route": ...}
TTL:   CACHE_TTL seconds, then Redis deletes it by itself.

Only the finished answer is cached (never individual stream chunks).
If Redis is down we just skip the cache (fail open) instead of breaking chat.
"""
import hashlib
import json
import logging

import redis.asyncio as redis

from app import config

log = logging.getLogger("smartroute")
redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)


def make_cache_key(message: str, history: list[dict] | None = None) -> str:
    """Make a key that includes the conversation leading up to this message."""
    # Cache results must depend on history: the same question can have a very
    # different answer after an earlier exchange.
    normalized = {
        "message": " ".join(message.lower().split()),
        "history": [
            {"role": item["role"], "content": " ".join(item["content"].lower().split())}
            for item in (history or [])
        ],
    }
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return "cache:" + hashlib.sha256(payload.encode()).hexdigest()


async def get_cached(message: str, history: list[dict] | None = None) -> dict | None:
    """Return the cached answer dict, or None on miss / cache disabled / Redis error."""
    if not config.CACHE_ENABLED:
        return None
    try:
        value = await redis_client.get(make_cache_key(message, history))
    except redis.RedisError:
        log.warning("cache lookup failed, continuing without cache")
        return None
    answer = json.loads(value) if value else None
    return answer if answer and "info" in answer else None  # ignore entries from older versions


async def save_cached(message: str, answer: dict, history: list[dict] | None = None) -> None:
    if not config.CACHE_ENABLED:
        return
    try:
        await redis_client.set(make_cache_key(message, history), json.dumps(answer), ex=config.CACHE_TTL)
    except redis.RedisError:
        log.warning("cache write failed")
