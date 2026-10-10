# SmartRoute — Fault-Tolerant Multi-Provider LLM Gateway

A small chatbot that shows how an LLM gateway works: requests are routed automatically to one of several free-tier LLM providers, retried and failed over when a provider misbehaves, cached, rate limited, streamed to the browser, and monitored.

It is a learning/portfolio project, not a production system. New to these ideas? Start with [docs/beginner-guide.md](docs/beginner-guide.md).

## Why this project exists

Single-provider chatbots break when that provider rate-limits or goes down. This project demonstrates the usual fix: put a gateway (LiteLLM) between the app and the providers, and let the gateway handle routing, retries and fallbacks, while the app stays free of provider-specific code.

## Architecture

```
React (Vite)
   │  HTTP POST + SSE stream
   ▼
FastAPI  ── auth, rate limit (Redis), cache (Redis), metrics (Prometheus)
   │  OpenAI-compatible API
   ▼
LiteLLM gateway ── auto router → logical model group → retry → fallback
   │                                │
   │             ┌──────────────────┼───────────────────┐
   │        coding-model      research-model       general-model / reasoning-model
   │        (OpenRouter)        (Gemini)               (Groq / OpenRouter)
   │             └── fallbacks: the other providers ──┘
   ▼
LangSmith (traces)         Prometheus ◄── FastAPI + LiteLLM ──► Grafana
```

FastAPI is the application API; LiteLLM is the only gateway. There is no custom gateway in between.

## Features

- Automatic routing with LiteLLM's built-in complexity router (no custom ML)
- 3 free-tier providers: OpenRouter, Google Gemini, Groq
- Retry, fallback and cooldown, all configured in `litellm/config.yaml`
- Server-Sent Events streaming
- Application-level recovery when a provider fails mid-stream
- Redis rate limiting (fixed window) and response caching
- Input guardrail (LiteLLM content filter): blocks SSNs, card numbers, cloud keys, prompt-injection and harmful prompts; masks emails and phone numbers
- API-key auth, CORS, request size limit
- LangSmith traces, Prometheus metrics, Grafana dashboard
- Docker Compose, pytest tests, GitHub Actions CI

## Technology stack

React + Vite (react-markdown) · FastAPI · LiteLLM proxy (pinned to 1.104.0) · Redis · LangSmith · Prometheus · Grafana · Docker Compose · pytest · ruff · GitHub Actions

## Request lifecycle

1. React `POST /chat` with `X-API-Key` header (`chatbot-frontend/src/api.js`).
2. FastAPI checks the API key, then the Redis rate limit (`main.py`, `rate_limit.py`).
3. FastAPI loads the recent conversation for the browser session from Redis, then `streaming.py` looks for a cache entry for that exact context. Hit → send the cached text and finish.
4. Miss → `chat.py` sends the system prompt, saved conversation, and latest message to LiteLLM using the model `smart-router`.
5. LiteLLM's complexity router picks a logical group; the group's deployment answers (retries/fallbacks happen inside LiteLLM).
6. Tokens stream back through FastAPI as SSE events to React.
7. When finished, the full answer is cached, metrics and logs are written, and LangSmith has the trace (recorded by LiteLLM).

## Routing

`smart-router` uses LiteLLM's `complexity_router`: a fast heuristic score (code present, reasoning words, length, technical terms, …) that picks one of four tiers. Each tier maps to a logical model group:

| Tier | Logical group | Primary provider | Fallbacks |
|---|---|---|---|
| SIMPLE | general-model | Groq | Gemini, OpenRouter |
| MEDIUM | research-model | Gemini | OpenRouter, Groq |
| COMPLEX | coding-model | OpenRouter | Groq, Gemini |
| REASONING | reasoning-model | OpenRouter | Gemini, Groq |

Honest notes: it is a heuristic, not a classifier. With LiteLLM's default thresholds almost everything landed in SIMPLE/MEDIUM in my tests, so `tier_boundaries` in `litellm/config.yaml` are lowered. Expect some prompts to land in an unexpected group. FastAPI never names a provider; all model IDs are in `litellm/config.yaml`.

## Fallback and retry

- **Retry**: same deployment, `num_retries: 1`, for retryable errors (429, 5xx, timeout, connection error).
- **Fallback**: after retries are used up, LiteLLM tries the next deployment in the group's `fallbacks` list.
- **Cooldown**: a deployment that fails (`allowed_fails: 1`) is skipped for `cooldown_time: 30` seconds.
- If everything fails, FastAPI sends an SSE `error` event with a friendly message.
- **No silent paid fallback**: every OpenRouter model ends in `:free`, Groq/Gemini are used with free-tier keys, and a test (`test_litellm_config.py`) enforces the `:free` rule.

## Guardrail

Configured in the `guardrails:` section of `litellm/config.yaml` using LiteLLM's built-in `litellm_content_filter` (no custom code, no extra service). It runs `pre_call` on every request, before routing:

| Action | What |
|---|---|
| MASK (continue with a placeholder like `[EMAIL_REDACTED]`) | email, US phone |
| BLOCK (HTTP 400) | US SSN, Visa/Mastercard/Amex numbers, AWS keys, GitHub tokens, prompt-injection (jailbreak, system-prompt extraction), self-harm, child safety, violence and weapons (high severity only) |

A blocked prompt is never sent to a provider and is not retried. The backend turns the 400 into an SSE `blocked` event (UI shows a "Blocked by guardrail" card), counts it in `llm_guardrail_blocked_total{reason}` and logs `status=blocked reason=...`. Limitations: it is keyword/regex based, so it has false positives and misses; at `medium` severity it blocked "kill a stuck process" and "bomb calorimeter", so violence/weapons use `high`. Only prompts are checked, not model answers, and masking only covers the prompt text (not the cache key hash). Not a substitute for real moderation.

## Rate limiting

Fixed-window counter in Redis: key `rate:<hash of api key>:<unix time // window>`, `INCR` on each request, `EXPIRE` set on first use. Above `RATE_LIMIT_REQUESTS` per `RATE_LIMIT_WINDOW` seconds → HTTP 429. Shared across FastAPI instances. A client can burst up to 2× the limit around a window boundary. If Redis is down the limiter fails open (logs a warning).

## Redis caching

Key `cache:<sha256 of normalized message and prior conversation>`, value JSON `{text, route, provider}`, TTL `CACHE_TTL`. Only completed answers are cached, never stream chunks, and answers that needed mid-stream recovery are not cached. Including the preceding conversation prevents reuse of an answer produced for a different context.

## Request inspector (UI)

Each answer has a "View details" link that opens a popup showing: router tier and score → logical group → provider, the exact model, tries (retries + fallbacks), latency, tokens, cost, cache/recovery flags and request ID, plus session totals. "Billed" is always $0 on free tiers; "list-price est." is LiteLLM's estimate at public prices, shown for learning only. LiteLLM's headers don't say *which* deployments failed before the successful one, only how many retries/fallbacks happened; for that, use the LangSmith error runs or LiteLLM's Prometheus metrics.

## Streaming

`POST /chat` returns `text/event-stream`. Events are `data: {json}` lines: `token` (`text`), `meta` (provider, model, router tier/score, retries, fallbacks, sent as soon as a provider accepts), `done` (latency, tokens, list-price cost estimate, `cached`, `recovered`), or `error`. The browser reads them with `fetch` + a stream reader because `EventSource` cannot send POST bodies or custom headers.

## Mid-stream failure recovery

LiteLLM's retry/fallback covers failures *before an answer starts*. If a provider dies *after* tokens were already sent, `continue_after_failure()` in `backend/app/streaming.py`:

1. keeps the text streamed so far,
2. logs a warning and increments `llm_provider_errors_total`,
3. calls `RECOVERY_MODEL` (default `fallback-groq`) with the original question, the partial answer as an assistant message, and an instruction to continue without repeating,
4. streams the continuation to the same client.

Limitations: the continuation is best-effort (the model may repeat or drift slightly), only one recovery attempt is made, and it uses a single fixed recovery model. It is covered by a unit test with a simulated broken stream (`tests/test_fallback.py`); the continuation call itself was checked live against the real recovery model, but a real mid-stream provider outage has not been reproduced.

## LangSmith observability

LiteLLM's built-in `langsmith` callback (in `litellm/config.yaml`) sends every LLM call to LangSmith: input/output, model and provider, latency, token usage and errors, and the routing decision (tier, routed model). The backend passes the `request_id`, which appears in each run under `extra.requester_metadata.request_id`. Set `LANGSMITH_API_KEY` and `LANGSMITH_PROJECT` in `.env`; leave the key empty to disable. Note that prompts and answers are sent to LangSmith, so don't put sensitive data in the demo. The backend itself never logs prompts or keys.

## Prometheus and Grafana

Backend `/metrics` (labels are small fixed sets, never prompts or request IDs):

| Metric | Meaning |
|---|---|
| `llm_requests_total{route,provider,status}` | chat requests (`success`, `recovered`, `cache_hit`, `error`) |
| `llm_requests_failed_total{route}` | requests that ended in an error |
| `llm_fallback_total{route,provider}` | answers produced by a fallback deployment |
| `llm_retry_total{route}` | LiteLLM retries before an answer |
| `llm_request_duration_seconds{route}` | latency histogram |
| `llm_cache_hits_total` / `llm_cache_misses_total` | cache effectiveness |
| `llm_rate_limit_total` | requests rejected with 429 |
| `llm_guardrail_blocked_total{reason}` | prompts rejected by the guardrail |
| `llm_provider_errors_total{provider}` | mid-stream provider failures seen by the backend |
| `llm_tokens_total{provider,type}` | prompt/completion tokens used |
| `llm_estimated_cost_usd_total` | LiteLLM list-price estimate (free tiers are not billed) |

Prometheus also scrapes LiteLLM's own `/metrics` for per-deployment failures and cooldowns. Grafana (http://localhost:3001) has one provisioned dashboard "SmartRoute": total requests, error rate, p95 latency, fallbacks, retries, cache hit rate, rate-limit count, requests by route and by provider.

Note: when a request fails before any deployment answers, `route`/`provider` are `unknown`; for fallback answers the route label is `fallback` (the deployment's group).

## Project structure

```
chatbot-backend/    FastAPI app (app/), tests/, requirements*.txt, Dockerfile
chatbot-frontend/   React + Vite chat UI
litellm/config.yaml Gateway: model groups, routing, retries, fallbacks, callbacks
monitoring/         prometheus.yml, Grafana provisioning + dashboard.json
docs/               beginner-guide.md, interview-guide.md, resume-bullets.md
docker-compose.yml  backend, frontend, redis, litellm, prometheus, grafana
```

## Local setup (Docker Compose, recommended)

```bash
cp .env.example .env        # then fill in the keys below
docker compose up --build
```

| Service | URL |
|---|---|
| Chat UI | http://localhost:3000 |
| Backend | http://localhost:8000 (`/health`, `/metrics`) |
| LiteLLM | http://localhost:4000 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3001 |

Get free keys: [OpenRouter](https://openrouter.ai/keys), [Google AI Studio](https://aistudio.google.com/apikey), [Groq](https://console.groq.com/keys), optionally [LangSmith](https://smith.langchain.com).

Without Docker: run Redis, then `litellm --config litellm/config.yaml` (needs `pip install "litellm[proxy]==1.104.0" prometheus_client`), then in `chatbot-backend`: `pip install -r requirements.txt && uvicorn app.main:app --reload`, then in `chatbot-frontend`: `cp .env.example .env && npm install && npm run dev`.

## Environment variables

See `.env.example`. Key ones: `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `API_KEY` (clients send it as `X-API-Key`), `LITELLM_MASTER_KEY`, `REDIS_URL`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `CACHE_ENABLED`, `CACHE_TTL`, `MEMORY_ENABLED`, `MEMORY_TTL`, `MEMORY_MAX_TURNS`, `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW`. `.env` is git-ignored. The frontend's `VITE_API_KEY` ends up in the browser bundle, which is acceptable for a local demo only.

## Testing

```bash
cd chatbot-backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check . && pytest -q
```

Tests use fake Redis and a fake LiteLLM stream (no network): health, validation, auth, rate limit, cache hit skipping the LLM, mid-stream recovery, graceful failure, metrics, and a check that `litellm/config.yaml` fallbacks are valid and OpenRouter models are `:free`. CI (`.github/workflows/ci.yml`) runs lint + tests and the frontend build.

## Example requests

```bash
curl -N -X POST http://localhost:8000/chat \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"message": "Write a Python function that reverses a linked list"}'

curl http://localhost:8000/metrics | grep llm_
```

## Failure scenarios

| Scenario | What happens |
|---|---|
| Provider returns 429 / 5xx / times out | LiteLLM retries once, then falls back; cooldown for 30 s |
| Provider dies after partial output | `continue_after_failure()` continues on the recovery model |
| All providers fail | SSE `error` event: "All AI providers are unavailable…" |
| Prompt trips the guardrail | SSE `blocked` event, no provider called |
| Too many requests | HTTP 429 from the rate limiter |
| Missing/wrong API key | HTTP 401 |
| Redis down | cache and rate limit are skipped (fail open), chat keeps working |

## Limitations

- Free-tier models and limits change; check `litellm/config.yaml` if a model stops working (Gemini sometimes answers 503 "high demand"; that is exactly what the fallbacks are for).
- Routing is a heuristic.
- Redis-backed conversation memory keeps the most recent 12 completed turns per browser session for 24 hours by default. Tune `MEMORY_MAX_TURNS` and `MEMORY_TTL` in `.env`.
- One shared API key; the rate limit is per key, not per end user.
- Mid-stream recovery is best-effort; tested with a simulated failure plus a live continuation call.
- The frontend embeds the API key (demo only). No TLS, no secrets manager.
- Not load tested; no claim about scale.

## Future improvements

Per-user keys and limits, semantic caching, a second recovery attempt, alerting rules in Prometheus, tracing the cache/rate-limit steps in LangSmith, HTTPS and a real auth flow.
