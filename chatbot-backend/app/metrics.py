"""Prometheus metrics. Labels are small fixed sets (route/provider/status) so the
number of time series stays low - never put the prompt or request id in a label."""
from prometheus_client import Counter, Histogram

requests_total = Counter("llm_requests_total", "Chat requests", ["route", "provider", "status"])
requests_failed_total = Counter("llm_requests_failed_total", "Chat requests that ended in an error", ["route"])
fallback_total = Counter("llm_fallback_total", "Requests answered by a fallback deployment", ["route", "provider"])
retry_total = Counter("llm_retry_total", "LiteLLM retries before an answer", ["route"])
request_duration = Histogram("llm_request_duration_seconds", "Time to finish a chat request", ["route"])
cache_hits_total = Counter("llm_cache_hits_total", "Responses served from Redis")
cache_misses_total = Counter("llm_cache_misses_total", "Cache lookups that missed")
rate_limit_total = Counter("llm_rate_limit_total", "Requests rejected by the rate limiter")
provider_errors_total = Counter("llm_provider_errors_total", "Failures seen by the backend (e.g. mid-stream)", ["provider"])
tokens_total = Counter("llm_tokens_total", "Tokens used", ["provider", "type"])  # type = prompt | completion
estimated_cost_usd_total = Counter("llm_estimated_cost_usd_total", "LiteLLM list-price cost estimate (free tiers are not billed)")
guardrail_blocked_total = Counter("llm_guardrail_blocked_total", "Prompts rejected by the guardrail", ["reason"])
