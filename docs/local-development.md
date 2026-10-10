# Local development

Docker Compose is the recommended way to run SmartRoute. It starts the frontend, backend, LiteLLM gateway, Redis, Prometheus, and Grafana with the correct local networking.

## Prerequisites

- Docker Desktop, with its engine running
- At least one provider key from [OpenRouter](https://openrouter.ai/keys), [Google AI Studio](https://aistudio.google.com/apikey), or [Groq](https://console.groq.com/keys)

For a non-Docker run, install Python 3.12+ and Node.js 20+ as well.

## Configure the project

From the repository root:

```bash
cp .env.example .env
```

Open `.env` and set the application keys plus the provider keys you intend to use.

```env
API_KEY=replace-with-a-long-random-value
LITELLM_MASTER_KEY=sk-replace-with-another-long-random-value

OPENROUTER_API_KEY=
GEMINI_API_KEY=
GROQ_API_KEY=
```

`LANGSMITH_API_KEY` is optional. Leave it empty to disable LangSmith traces. Do not commit `.env`; it contains secrets and is ignored by Git.

### Runtime settings

| Variable | Default | Purpose |
|---|---:|---|
| `CACHE_ENABLED` | `true` | Enables Redis response caching. |
| `CACHE_TTL` | `300` | Cache lifetime in seconds. |
| `MEMORY_ENABLED` | `true` | Enables Redis conversation memory. |
| `MEMORY_TTL` | `86400` | Conversation lifetime in seconds. |
| `MEMORY_MAX_TURNS` | `12` | Completed user/assistant exchanges retained per session. |
| `RATE_LIMIT_REQUESTS` | `10` | Requests permitted per fixed window and API key. |
| `RATE_LIMIT_WINDOW` | `60` | Fixed-window length in seconds. |

## Run with Docker Compose

Start Docker Desktop and wait until it reports that the engine is running. Then, from the repository root:

```bash
docker compose up --build
```

Use `Ctrl+C` to stop the foreground process. To run it in the background:

```bash
docker compose up --build -d
```

Check status and backend logs:

```bash
docker compose ps
docker compose logs -f backend
```

Open the chat UI at http://localhost:3000. The backend health check is http://localhost:8000/health.

### Stop services

```bash
docker compose stop
```

`docker compose down` removes the containers and network. Redis currently has no named volume, so removing its container also removes its cache and conversation memory.

## Run without Docker

You still need local Redis and LiteLLM. Start each component in a separate terminal after configuring the root `.env` file.

### 1. Start Redis

Install Redis through your operating system's package manager, start it, then verify it:

```bash
redis-cli ping
```

Expected output:

```text
PONG
```

### 2. Start LiteLLM

```bash
python -m venv .litellm-venv
source .litellm-venv/bin/activate
pip install "litellm[proxy]==1.104.0" prometheus_client
litellm --config litellm/config.yaml --port 4000
```

### 3. Start FastAPI

```bash
cd chatbot-backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

### 4. Start the frontend

```bash
cd chatbot-frontend
cp .env.example .env
npm install
npm run dev
```

Vite prints the local URL, normally http://localhost:5173.

## Verify the application

Health check:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

Send a streaming request:

```bash
curl -N -X POST http://localhost:8000/chat \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"message":"Explain what Redis is in one sentence."}'
```

The command emits `data: {...}` events. Browser sessions add a session ID automatically. To use memory with curl, add `"session_id":"my-session"` to the JSON request body.

## Run checks

Backend:

```bash
cd chatbot-backend
source .venv/bin/activate
ruff check .
pytest -q
```

Frontend production build:

```bash
cd chatbot-frontend
npm run build
```

## Troubleshooting

### Docker cannot connect to `docker.sock`

Start Docker Desktop and wait for its engine to start. Confirm it with:

```bash
docker info
```

Then retry `docker compose up --build`.

### A provider does not answer

Confirm its key in `.env`, then inspect the gateway logs:

```bash
docker compose logs -f litellm
```

LiteLLM retries and uses configured fallbacks. If all configured providers are unavailable, the browser receives a friendly error event.

### Memory disappears after `docker compose down`

This is expected because Redis has no named volume. `docker compose stop` keeps the current Redis container. For durable conversations, use a named Redis volume or an external persistent database.
