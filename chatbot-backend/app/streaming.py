"""Streams the answer to the client as Server-Sent Events (SSE).

Each SSE line is:  data: {json}\n\n  with one of these shapes:
    {"type": "meta", ...}    sent as soon as a provider accepted the request (who answers, tries, tier)
    {"type": "token", "text": "..."}                         a piece of the answer
    {"type": "done", ...}    final stats: latency, tokens, estimated cost, cached, recovered
    {"type": "blocked", "message": "...", "reason": "us_ssn"}   guardrail rejected the prompt
    {"type": "error", "message": "..."}                       everything failed

Two different kinds of failure handling exist in this project:
  1. Request-level (before any text arrives): LiteLLM retries and falls back by itself.
  2. Mid-stream (provider dies after we already sent text): LiteLLM can't help because
     the client has already seen part of the answer, so continue_after_failure() below
     asks the recovery model to continue. That part is application-level logic.
"""
import json
import logging
import time
from collections.abc import AsyncIterator

from app import config, metrics
from app.cache import get_cached, save_cached
from app.chat import continuation_messages, conversation_messages, guardrail_reason, open_stream
from app.memory import save_turn

log = logging.getLogger("smartroute")

ERROR_TEXT = "All AI providers are unavailable right now. Please try again in a minute."


def sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def read_usage(chunk, usage: dict) -> None:
    """The last chunk of a stream has chunk.usage (tokens + LiteLLM's cost estimate)."""
    if getattr(chunk, "usage", None):
        usage["prompt_tokens"] = chunk.usage.prompt_tokens or 0
        usage["completion_tokens"] = chunk.usage.completion_tokens or 0
        usage["cost"] = (getattr(chunk.usage, "model_extra", None) or {}).get("cost", 0) or 0


async def continue_after_failure(
    history: list[dict], message: str, partial_text: str, request_id: str,
    recovery_info: dict, usage: dict,
) -> AsyncIterator[str]:
    """Recovery: ask the recovery model to finish an answer that was cut off.

    Receives the user's question and the text already streamed ("" if nothing arrived).
    Yields only NEW text pieces, so the client just keeps appending.
    Fills `recovery_info` with who answered (for the UI) and `usage` with token counts.
    """
    if partial_text:
        messages = continuation_messages(history, message, partial_text)
    else:
        messages = conversation_messages(history, message)
    info, stream = await open_stream(config.RECOVERY_MODEL, messages, request_id)
    recovery_info.update(info)
    async for chunk in stream:
        read_usage(chunk, usage)
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def record_metrics(info: dict, usage: dict, status: str, latency: float) -> None:
    route, provider = info["route"], info["provider"]
    metrics.requests_total.labels(route, provider, status).inc()
    metrics.request_duration.labels(route).observe(latency)
    metrics.tokens_total.labels(provider, "prompt").inc(usage["prompt_tokens"])
    metrics.tokens_total.labels(provider, "completion").inc(usage["completion_tokens"])
    metrics.estimated_cost_usd_total.inc(usage["cost"])


async def stream_chat(
    message: str, history: list[dict], session_id: str | None, request_id: str,
) -> AsyncIterator[str]:
    """Main generator behind POST /chat: cache -> LiteLLM stream -> (recovery) -> cache."""
    start = time.time()

    cached = await get_cached(message, history)
    if cached:
        metrics.cache_hits_total.inc()
        metrics.requests_total.labels(cached["route"], cached["provider"], "cache_hit").inc()
        log.info("request_id=%s route=%s provider=%s status=cache_hit latency=%.2f",
                 request_id, cached["route"], cached["provider"], time.time() - start)
        yield sse({"type": "meta", **cached["info"], "retries": 0, "fallbacks": 0, "attempts": 0})
        yield sse({"type": "token", "text": cached["text"]})
        await save_turn(session_id, message, cached["text"])
        yield sse({"type": "done", "request_id": request_id, "cached": True, "recovered": False,
                   "latency": round(time.time() - start, 2),
                   "prompt_tokens": 0, "completion_tokens": 0, "cost": 0})  # a cache hit uses nothing
        return
    if config.CACHE_ENABLED:
        metrics.cache_misses_total.inc()

    # info = who is answering; usage = tokens and cost; both shown in the UI
    info = {"route": "unknown", "provider": "unknown", "model": "unknown", "tier": "", "score": "",
            "retries": 0, "fallbacks": 0}
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0}
    text = ""          # everything streamed to the client so far (the "prefix" for recovery)
    recovered_by = None
    try:
        try:
            info, stream = await open_stream(
                config.ROUTER_MODEL, conversation_messages(history, message), request_id,
            )
            if info["retries"]:
                metrics.retry_total.labels(info["route"]).inc(info["retries"])
            if info["fallbacks"]:
                metrics.fallback_total.labels(info["route"], info["provider"]).inc()
                log.warning("request_id=%s route=%s provider=%s fallback_used=%d tier=%s",
                            request_id, info["route"], info["provider"], info["fallbacks"], info["tier"])
            yield sse({"type": "meta", **info, "attempts": 1 + info["retries"] + info["fallbacks"]})
            async for chunk in stream:
                read_usage(chunk, usage)
                if chunk.choices and chunk.choices[0].delta.content:
                    piece = chunk.choices[0].delta.content
                    text += piece
                    yield sse({"type": "token", "text": piece})
        except Exception as error:
            # Either LiteLLM exhausted its fallbacks (text == "") or the stream broke midway.
            if not text:
                raise
            metrics.provider_errors_total.labels(info["provider"]).inc()
            log.warning("request_id=%s route=%s provider=%s error=%s stream_failed_after_chars=%d fallback=%s",
                        request_id, info["route"], info["provider"], type(error).__name__, len(text),
                        config.RECOVERY_MODEL)
            recovery_info: dict = {}
            async for piece in continue_after_failure(history, message, text, request_id, recovery_info, usage):
                text += piece
                yield sse({"type": "token", "text": piece})
            recovered_by = f'{recovery_info["provider"]}/{recovery_info["model"]}'
    except Exception as error:
        reason = guardrail_reason(error)
        if reason:  # not a provider failure: the prompt itself was refused, nothing was retried
            metrics.guardrail_blocked_total.labels(reason).inc()
            metrics.requests_total.labels("none", "none", "blocked").inc()
            log.warning("request_id=%s status=blocked reason=%s", request_id, reason)
            yield sse({"type": "blocked", "reason": reason, "request_id": request_id,
                       "message": "Your message was blocked by the safety guardrail."})
            return
        metrics.requests_total.labels(info["route"], info["provider"], "error").inc()
        metrics.requests_failed_total.labels(info["route"]).inc()
        metrics.request_duration.labels(info["route"]).observe(time.time() - start)
        log.error("request_id=%s route=%s provider=%s status=error error=%s latency=%.2f",
                  request_id, info["route"], info["provider"], type(error).__name__, time.time() - start)
        yield sse({"type": "error", "message": ERROR_TEXT, "attempts": 1 + info["retries"] + info["fallbacks"]})
        return

    latency = time.time() - start
    status = "recovered" if recovered_by else "success"
    record_metrics(info, usage, status, latency)
    log.info("request_id=%s route=%s provider=%s tier=%s status=%s latency=%.2f tokens=%d",
             request_id, info["route"], info["provider"], info["tier"], status, latency,
             usage["prompt_tokens"] + usage["completion_tokens"])
    if text and not recovered_by:  # a stitched-together answer is not cached
        await save_cached(message, {"text": text, "route": info["route"], "provider": info["provider"],
                                    "info": info, "usage": usage}, history)
    await save_turn(session_id, message, text)
    yield sse({"type": "done", "request_id": request_id, "cached": False, "recovered": bool(recovered_by),
               "recovered_by": recovered_by, "latency": round(latency, 2), **usage})
