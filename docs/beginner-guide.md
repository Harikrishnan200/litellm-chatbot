# Beginner Guide to SmartRoute

This guide assumes you know basic Python and have heard of APIs. Everything else is explained here.

## Part 1 — Concepts

**1. What is an LLM?** A Large Language Model (like Gemini, Llama or GPT-OSS) is a program that predicts text. You send it a prompt, it sends back text. Providers host them and let you call them over HTTP with an API key.

**2. Why use multiple providers?** Free tiers have limits (requests per minute/day), and any provider can have outages. Different models are also better at different things. With several providers, one failing doesn't take your app down.

**3. What is an LLM gateway?** A service that sits between your app and the LLM providers. Your app talks to one place; the gateway decides which provider to use and handles failures. Think of it like a phone switchboard.

**4. What is LiteLLM?** An open-source gateway. You describe your providers and rules in one YAML file (`litellm/config.yaml`), and it exposes a single OpenAI-style API. It already implements routing, retries, fallbacks and cooldowns, so we don't write them ourselves.

**5. What is model routing?** Choosing which model answers a request. We use LiteLLM's *complexity router*: it scores the prompt (does it contain code? reasoning words? is it long?) and picks a tier. Each tier is mapped to a *logical model group* (`coding-model`, `research-model`, `general-model`, `reasoning-model`). A group is a name; the real provider model behind it is configured in the YAML. It's a heuristic, so it's sometimes "wrong"; that's acceptable for this project.

**6. What is fallback?** If the chosen deployment fails, try a different one. Example: `coding-model` is on OpenRouter; if OpenRouter fails, try Groq, then Gemini.

**7. Retry vs fallback.** *Retry* = try the **same** deployment again (good for a one-off blip). *Fallback* = try a **different** deployment (good when that provider is rate-limited or down). We do one retry, then fallback, because endless retries make users wait.

**8. What is rate limiting?** Capping how many requests a client can make in a time window (here: 10 per minute per API key). It protects the free-tier quotas from being burned by one client. Exceeding it returns HTTP 429.

**8b. What is a guardrail?** A safety check that inspects the prompt before it reaches a model. Ours (in `litellm/config.yaml`) blocks things like social security numbers, credit-card numbers and "ignore your instructions" attacks, and masks emails/phone numbers. A blocked prompt costs nothing and never leaves your system. It is simple pattern/keyword matching, so it is helpful but not perfect.

**9. Why Redis?** Redis is a fast in-memory key-value store. This project uses it for rate counters, cached answers, and short-term conversation memory. Those values can be shared by several backend copies and expire automatically with a TTL.

**10. What is caching?** Remembering a result so you don't compute it again. A cached answer is used only when both the new question and the conversation before it are the same. That saves a provider call without accidentally using an answer from the wrong chat context. Risk: answers can be stale, and non-deterministic questions ("tell me a joke") can repeat.

**10b. What is conversation memory?** The browser has a random session ID saved in local storage. After every successful answer, Redis saves the user message and answer for that session. The next request includes recent saved turns, so a follow-up such as "What was my name?" has context. The project keeps the newest 12 turns for 24 hours by default.

**11. What is streaming?** Instead of waiting for the whole answer, the server sends it piece by piece (like ChatGPT typing). We use **Server-Sent Events (SSE)**: a normal HTTP response that stays open and sends lines like `data: {...}`. It's simple and one-directional, which fits "server pushes tokens".

**12. What if a provider fails mid-stream?** The user has already seen half an answer, so LiteLLM's normal fallback can't simply restart. Our code keeps the text so far, then asks a fallback model: "here's the question and what you already wrote; continue without repeating." The user just sees the answer keep going. This is best-effort.

**13. What is LangSmith?** A tracing tool for LLM apps. It records each LLM call: prompt, answer, model, latency, tokens, errors. LiteLLM sends this automatically via a callback. It answers "what exactly did the model get and say, and why was it slow?".

**14. What is Prometheus?** A database for numeric metrics. It periodically fetches (`scrapes`) `/metrics` from our services. Metrics are counters ("how many requests"), histograms ("how long did they take"), etc.

**15. What is Grafana?** A dashboard tool that draws charts from Prometheus data. LangSmith = per-request detail; Prometheus/Grafana = overall health over time.

**16. Why FastAPI?** Small, fast to write, great with async code (needed for streaming) and Pydantic validation.

**17. Why React?** The standard way to build interactive UIs; the chat window updates as tokens arrive.

**18. Why Docker Compose?** One command (`docker compose up`) starts all six services with the right networking, so you don't install Redis/Prometheus/Grafana by hand.

## Part 2 — Lifecycles

**19. Normal request**

1. Browser → `POST /chat` with the `X-API-Key` header.
2. FastAPI: key valid? Under the rate limit? (Redis counter)
3. Load recent conversation memory, then check Redis for a cached answer for this exact message and context. Hit → send stored text, done.
4. Miss → ask LiteLLM for model `smart-router`, with the saved turns plus the new prompt.
5. Complexity router picks a tier → logical group → deployment (e.g. Groq).
6. Provider streams tokens → LiteLLM → FastAPI → browser, which appends them.
7. Finished: store the completed exchange in Redis memory, cache eligible answers, update metrics, and write a log line. LiteLLM sends the trace to LangSmith.

**20. Failure lifecycle**

- *Provider returns 429/500/timeout before any text*: LiteLLM retries once → falls back to the next deployment → ... → if all fail, FastAPI sends an `error` event and the UI shows "All AI providers are unavailable". The failed deployment is in cooldown for 30 s so later requests skip it.
- *Provider breaks after some text*: `continue_after_failure()` calls the recovery model with the partial text and keeps streaming.
- *Prompt blocked by the guardrail*: LiteLLM answers HTTP 400 before routing; the backend sends a `blocked` event and the UI shows the reason. No retries, no fallback.
- *Too many requests*: 429 before any LLM call.
- *Redis down*: caching and rate limiting are skipped with a warning; chat still works.

## Part 3 — The source files

### litellm/config.yaml
The gateway's brain. `model_list` defines deployments (`model_name` = name the app uses, `litellm_params.model` = `<provider>/<model id>`, `model_info.id` = label `<route>-<provider>`). `smart-router` is the auto router. `router_settings` has retries, timeout, cooldown and the `fallbacks` lists. `litellm_settings` turns on LangSmith and Prometheus. **To change a model, edit only this file.**

### chatbot-backend/app/main.py
The front door. Creates the FastAPI app, adds CORS and a request-size check, defines `GET /health`, `GET /metrics` and `POST /chat`. For `/chat` it runs the API-key check (`require_api_key`), generates a request ID, applies the rate limit, then returns a `StreamingResponse` fed by `stream_chat()`.

### chatbot-backend/app/config.py
Reads environment variables into constants (API key, URLs, cache TTL, memory limits, rate limits). No provider model names live here.

### chatbot-backend/app/models.py
`ChatRequest`: the JSON body must have `message` of 1–4000 characters. It may also include a short `session_id`, which tells the backend which conversation memory to load. Invalid bodies receive HTTP 422 automatically.

### chatbot-backend/app/chat.py
The only file that talks to the LLM gateway. `open_stream()` calls LiteLLM (using the standard OpenAI client pointed at LiteLLM) and returns the stream plus info read from response headers (`read_headers()` turns the `x-litellm-model-id` label into route + provider, and reads retry/fallback counts). `conversation_messages()` and `continuation_messages()` build prompts from the system instruction, saved history, and latest message.

### chatbot-backend/app/streaming.py
`stream_chat()` is the heart: cache lookup → open stream → forward tokens as SSE → memory/cache save → metrics/logs. `continue_after_failure()` is the mid-stream recovery. It receives the conversation, original message, and partial text, then yields only new text.

### chatbot-backend/app/cache.py
Redis cache. Key `cache:<sha256(normalized message + prior conversation)>`, value = JSON of the answer, TTL = `CACHE_TTL`. `get_cached()` / `save_cached()`. Errors are swallowed (logged) so Redis problems never break chat.

### chatbot-backend/app/memory.py
Redis conversation memory. `get_history()` returns valid saved user and assistant messages for a session. `save_turn()` appends a completed exchange, keeps the newest `MEMORY_MAX_TURNS`, and refreshes the `MEMORY_TTL`. Like the cache, it fails open when Redis is unavailable.

### chatbot-backend/app/rate_limit.py
`is_rate_limited(api_key)`: key `rate:<hash>:<window number>`; `INCR`; set expiry on first hit; return `count > limit`. The window number is `unix_time // window_seconds`, so the counter resets by changing key.

### chatbot-backend/app/metrics.py
Defines the Prometheus counters/histogram. Labels are only `route`, `provider`, `status`: bounded sets. We never label with prompts or request IDs because every distinct value creates a new time series.

### chatbot-backend/tests/
Fake Redis + fake LLM stream (`conftest.py`) so tests run offline. Files test health/auth/validation, rate limiting, cache, conversation memory, mid-stream recovery, and the validity of `litellm/config.yaml`.

### chatbot-frontend/src/
`api.js`: `streamChat()` sends the POST and parses SSE events from the response body. `components/Chat.jsx`: message list, input form; appends tokens to the last message and shows route/provider under each answer. `App.jsx` and `main.jsx` are boilerplate.

### monitoring/
`prometheus.yml` says what to scrape (backend and LiteLLM). `grafana/provisioning/` auto-registers the data source and dashboard; `dashboard.json` defines the nine panels.

### docker-compose.yml, .env.example, .github/workflows/ci.yml
Compose wires the six services. `.env.example` lists every variable (copy to `.env`; never commit it). CI runs ruff + pytest and builds the frontend on every push.

## Try it yourself

1. `docker compose up --build`, open http://localhost:3000, ask "hi", then "Write a Python function to reverse a linked list". Note the route/provider shown.
2. Ask a follow-up such as "What did I ask you first?" to see conversation memory in action. Refresh the page: the saved conversation is restored.
3. Send 11 requests in a minute (curl loop): the 11th gets 429.
4. Put a wrong `GROQ_API_KEY` in `.env`, restart, ask "hi": watch the fallback in `docker compose logs backend` and in Grafana.
