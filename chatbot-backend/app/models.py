"""Request body for POST /chat. Pydantic rejects bad input with HTTP 422 for us."""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    # The browser generates a random ID and keeps it in local storage. It is
    # opaque to the backend and scopes the Redis conversation memory.
    session_id: str | None = Field(default=None, min_length=1, max_length=128)
