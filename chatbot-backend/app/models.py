"""Request body for POST /chat. Pydantic rejects bad input with HTTP 422 for us."""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
