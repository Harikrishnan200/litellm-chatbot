"""All settings come from environment variables (see .env.example).

Provider model IDs are NOT here - they live in litellm/config.yaml.
The backend only knows logical names such as "smart-router".
"""
import os

from dotenv import load_dotenv

load_dotenv()  # reads .env when running locally; in Docker the vars are injected


def _bool(name: str, default: str) -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes")


API_KEY = os.getenv("API_KEY", "")

# Where the LiteLLM gateway runs, and the key the backend uses to talk to it.
LITELLM_URL = os.getenv("LITELLM_URL", "http://localhost:4000")
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "")

# "smart-router" = LiteLLM picks the logical model group automatically.
ROUTER_MODEL = os.getenv("ROUTER_MODEL", "smart-router")
# Used only for mid-stream recovery (see streaming.py). Must exist in litellm/config.yaml.
RECOVERY_MODEL = os.getenv("RECOVERY_MODEL", "fallback-groq")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

CACHE_ENABLED = _bool("CACHE_ENABLED", "true")
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))  # seconds

# Conversation memory lives in Redis.  We retain a small, recent window so a
# long-running browser session does not eventually exceed the model context.
MEMORY_ENABLED = _bool("MEMORY_ENABLED", "true")
MEMORY_TTL = int(os.getenv("MEMORY_TTL", "86400"))  # 24 hours
MEMORY_MAX_TURNS = int(os.getenv("MEMORY_MAX_TURNS", "12"))

RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "10"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # seconds

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
MAX_REQUEST_BYTES = 16_000  # request size limit
