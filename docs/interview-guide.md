# Interview guide

Answers describe what this project actually implements. Where something is not implemented, it says so.

**1. Why did you use LiteLLM?**
It already provides routing, retries, fallbacks, cooldowns, a unified OpenAI-style API and callbacks (LangSmith, Prometheus). Writing that myself would be reinventing a well-tested piece and adds bugs. My code focuses on app concerns: auth, rate limit, cache, streaming, recovery.

**2. Why not call OpenAI/Gemini/Groq directly?**
Each has a different SDK and error behavior, and a direct call has no failover. With the gateway, the backend has no provider-specific code; changing or adding a model is a YAML edit.

**3. What is an LLM gateway?**
A layer between the app and LLM providers that centralizes routing, failover, observability and keys. Here it's the LiteLLM proxy container; FastAPI is just the application API in front of it.

**4. How does automatic routing work?**
The backend asks for the model `smart-router`. LiteLLM's complexity router scores the prompt with heuristics (code, reasoning markers, length, technical terms), picks a tier SIMPLE/MEDIUM/COMPLEX/REASONING, and each tier maps to a logical group. It is not ML and is imperfect; with default thresholds nearly everything fell in SIMPLE/MEDIUM, so I lowered `tier_boundaries` after testing sample prompts.

**5. How does fallback work?**
`router_settings.fallbacks` lists, per logical group, other deployments to try in order after retries fail. E.g. `coding-model` (OpenRouter) → Groq → Gemini.

**6. Retry vs fallback?**
Retry = same deployment again (`num_retries: 1`), for transient errors. Fallback = a different deployment. Retries are kept small so users don't wait long.

**7. Provider returns HTTP 429?**
LiteLLM retries once, then falls back to the next provider; the deployment goes into a 30 s cooldown so following requests skip it. The backend sees the final result, and the fallback shows in `llm_fallback_total` and logs.

**8. Provider times out?**
Timeout is 30 s (`router_settings.timeout`); a timeout is treated as a retryable error, so same path as 429.

**9. Provider fails while streaming?**
LiteLLM can't restart a stream the user already partly saw, so `continue_after_failure()` (backend/app/streaming.py) keeps the partial text and calls a recovery model with the question + partial answer + "continue without repeating". Limits: best-effort quality, one attempt, fixed recovery model, tested with a simulated failure rather than a real outage.

**10. Why Redis?**
Shared, fast, with automatic key expiry: perfect for rate-limit counters and cached answers even with multiple backend instances. I use it for only those two things.

**11. How does rate limiting work?**
Fixed window: key `rate:<hash of API key>:<time // window>`, `INCR`, `EXPIRE` on first hit, reject with 429 when over the limit (default 10/60 s). Drawback: bursts up to 2× across a window boundary; a sliding window or token bucket would fix that. Fails open if Redis is down.

**12. Why cache LLM responses?**
Saves latency, cost and free-tier quota for repeated questions. Cache key = SHA-256 of the normalized message, TTL 300 s, only complete answers.

**13. Risks of caching?**
Stale answers, repeated "creative" answers, leaking one user's answer to another if prompts include personal context (this app is single-turn with no user data, so the key is just the message), and caching bad answers. I don't cache recovered (stitched) answers. Semantic caching is not implemented.

**14. Why LangSmith?**
Per-request LLM visibility: prompt, response, model/provider, latency, tokens, errors. LiteLLM sends it via a callback so no custom code. Caveat: prompts leave my system, so it's optional (empty key = off).

**15. Why Prometheus?**
Numeric time-series for health and alerting: rates, error ratios, latency percentiles. Different job from LangSmith's per-call traces.

**16. Why Grafana?**
Turns Prometheus data into one dashboard (provisioned from JSON in the repo, so it's reproducible).

**17. What metrics did you collect?**
`llm_requests_total{route,provider,status}`, `llm_requests_failed_total`, `llm_fallback_total`, `llm_retry_total`, `llm_request_duration_seconds`, `llm_cache_hits_total`, `llm_cache_misses_total`, `llm_rate_limit_total`, `llm_provider_errors_total` (mid-stream failures), plus LiteLLM's own per-deployment metrics. Labels are low-cardinality on purpose.

**18. Why SSE?**
Streaming is one-way (server → client), SSE is plain HTTP, easy to proxy and simple in FastAPI. WebSockets are more than needed. Since `EventSource` can't POST or set headers, the frontend reads the SSE response with `fetch` and a stream reader.

**19. Why not Ollama?**
It needs local compute (GPU/RAM) and doesn't demonstrate multi-provider failover. Free cloud tiers keep the project runnable on any laptop.

**20. How does it stay free?**
Free API keys from three providers, OpenRouter models limited to `:free` variants (a test enforces it), no local models, no paid services. Free tiers have rate limits, which is exactly what the fallback logic handles.

**21. What if all providers fail?**
LiteLLM exhausts retries and fallbacks, the backend logs the error, increments the failure metric, and the client gets an SSE `error` event with a friendly message (no stack trace, no secrets).

**22. How would you scale it?**
FastAPI is stateless (state is in Redis), so run multiple replicas behind a load balancer; rate limits already work across replicas. Scale LiteLLM replicas too. I haven't load tested this, so I wouldn't claim numbers.

**23. Limitations?**
Heuristic routing; single-turn chat; one shared API key; best-effort mid-stream recovery; free-tier limits and model churn; API key embedded in the frontend bundle for the demo; route label for fallback answers is just "fallback".

**24. What would you improve for production?**
Per-user auth and limits, conversation memory, sliding-window limiter, semantic cache, Prometheus alert rules, secrets manager and TLS, proper integration tests against real providers, load testing, a smarter or learned router with evaluation data.

**25. Do you have guardrails?**
Yes, a pre-call input guardrail using LiteLLM's built-in content filter, configured in YAML: it blocks SSNs, card numbers, cloud keys, prompt-injection phrases and harmful categories, and masks emails/phones. Blocked prompts return HTTP 400 before routing, so there is no provider call, retry or fallback; the backend reports them as a `blocked` event and a `llm_guardrail_blocked_total` metric. Limits: keyword/regex based (I had to raise violence/weapons to `high` severity to stop false positives like "kill a process"), prompts only, no output moderation.
