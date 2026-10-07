"""Fixed-window rate limiter backed by Redis.

Algorithm: every API key gets a counter per time window.
    key   = rate:<hash of api key>:<window number>   (window number = unix time // WINDOW)
    INCR the key; if it was just created, EXPIRE it after WINDOW seconds.
    If the counter is above RATE_LIMIT_REQUESTS -> reject with HTTP 429.
Redis is shared, so the limit holds even with several FastAPI instances.
Downside: a client can burst at a window boundary (up to 2x). Fine for this project.
"""
import hashlib
import logging
import time

import redis.asyncio as redis

from app import config
from app.cache import redis_client

log = logging.getLogger("smartroute")


async def is_rate_limited(api_key: str) -> bool:
    """Count this request; return True if the client is over its limit."""
    window = int(time.time()) // config.RATE_LIMIT_WINDOW
    key = f"rate:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}:{window}"
    try:
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, config.RATE_LIMIT_WINDOW)
    except redis.RedisError:
        log.warning("rate limiter could not reach Redis, allowing request")
        return False
    return count > config.RATE_LIMIT_REQUESTS
