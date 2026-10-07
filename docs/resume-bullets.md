# Resume bullets

Pick 3–4. Numbers below are only things you can honestly say about this project; do not add scale claims.

- Built **SmartRoute**, a multi-provider LLM chatbot gateway using FastAPI and a pinned LiteLLM proxy, integrating OpenRouter, Google Gemini and Groq free-tier models behind four logical model groups selected by LiteLLM's complexity-based auto-routing.
- Implemented fault tolerance with per-group retry, ordered fallbacks and deployment cooldowns, plus an application-level recovery that continues a response on a fallback model when a provider fails mid-stream (SSE streaming to a React client).
- Added Redis-backed fixed-window rate limiting and response caching, API-key authentication, request size limits and graceful degradation when providers or Redis are unavailable.
- Instrumented the system with LangSmith LLM tracing, Prometheus metrics (requests, latency, fallbacks, retries, cache hit rate, rate-limit events) and a provisioned Grafana dashboard; packaged with Docker Compose, pytest tests (mocked providers) and GitHub Actions CI.
