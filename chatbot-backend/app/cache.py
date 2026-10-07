"""Response cache in Redis.

key:   cache:<sha256 of the normalized message>
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


def make_cache_key(message: str) -> str:
    # lower-case + collapse whitespace so "Hi  there" and "hi there" share an entry
    normalized = " ".join(message.lower().split())
    return "cache:" + hashlib.sha256(normalized.encode()).hexdigest()


async def get_cached(message: str) -> dict | None:
    """Return the cached answer dict, or None on miss / cache disabled / Redis error."""
    if not config.CACHE_ENABLED:
        return None
    try:
        value = await redis_client.get(make_cache_key(message))
    except redis.RedisError:
        log.warning("cache lookup failed, continuing without cache")
        return None
    answer = json.loads(value) if value else None
    return answer if answer and "info" in answer else None  # ignore entries from older versions


async def save_cached(message: str, answer: dict) -> None:
    if not config.CACHE_ENABLED:
        return
    try:
        await redis_client.set(make_cache_key(message), json.dumps(answer), ex=config.CACHE_TTL)
    except redis.RedisError:
        log.warning("cache write failed")
