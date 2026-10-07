"""Talks to the LiteLLM gateway. This is the ONLY place the backend calls an LLM.

We use the standard OpenAI client because the LiteLLM proxy speaks the OpenAI API.
We never name a provider here: we ask for a logical model ("smart-router") and
LiteLLM does routing, retries and fallbacks.
"""
from openai import AsyncOpenAI, BadRequestError

from app import config

client = AsyncOpenAI(
    base_url=config.LITELLM_URL,
    api_key=config.LITELLM_MASTER_KEY or "not-set",
    max_retries=0,  # LiteLLM already retries; don't multiply retries
)

SYSTEM_PROMPT = "You are a helpful assistant. Answer clearly and concisely."


async def open_stream(model: str, messages: list[dict], request_id: str):
    """Start a streaming chat call through LiteLLM.

    Returns (info, stream):
      info   - which deployment answered (read from LiteLLM response headers)
      stream - async iterator of chunks; each chunk has the next piece of text
    Raises an openai error if LiteLLM could not get an answer from any provider.
    """
    raw = await client.chat.completions.with_raw_response.create(
        model=model,
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},  # final chunk carries token counts + cost
        # metadata shows up on the LangSmith trace so we can find a request by id
        extra_body={"metadata": {"request_id": request_id}},
    )
    return read_headers(raw.headers), raw.parse()


def read_headers(headers) -> dict:
    """Turn LiteLLM response headers into a small dict.

    x-litellm-model-id is the label from litellm/config.yaml, e.g. "coding-openrouter"
    = "<route>-<provider>". Fallback deployments are labelled "fallback-<provider>".
    """
    deployment = headers.get("x-litellm-model-id", "unknown-unknown")
    route, _, provider = deployment.partition("-")
    return {
        "route": route,
        "provider": provider or "unknown",
        "model": headers.get("x-litellm-model-name", "unknown"),  # e.g. groq/openai/gpt-oss-20b
        "tier": headers.get("x-litellm-complexity-router-tier", ""),
        "score": headers.get("x-litellm-complexity-router-score", ""),
        "retries": int(headers.get("x-litellm-attempted-retries", 0) or 0),
        "fallbacks": int(headers.get("x-litellm-attempted-fallbacks", 0) or 0),
    }


def first_message(message: str) -> list[dict]:
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": message}]


def continuation_messages(message: str, partial_text: str) -> list[dict]:
    """Messages for mid-stream recovery: original question + the text already sent."""
    instruction = (
        "Your previous answer was cut off. Continue it from exactly where it stopped. "
        "Do not repeat the text already written and do not add an introduction."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": message},
        {"role": "assistant", "content": partial_text},
        {"role": "user", "content": instruction},
    ]


def guardrail_reason(error: Exception) -> str | None:
    """If LiteLLM's guardrail rejected the prompt, return why (e.g. "us_ssn"); otherwise None.

    A blocked prompt comes back as HTTP 400 with the text "Content blocked: ...".
    """
    if not isinstance(error, BadRequestError) or "Content blocked" not in str(error):
        return None
    fields = (error.body or {}).get("provider_specific_fields", {}) if isinstance(error.body, dict) else {}
    return fields.get("pattern") or fields.get("category") or "policy"
