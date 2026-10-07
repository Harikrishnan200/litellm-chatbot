"""FastAPI entry point: auth, rate limit, then hand the request to the streaming code."""
import logging
import secrets
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app import config, metrics
from app.models import ChatRequest
from app.rate_limit import is_rate_limited
from app.streaming import stream_chat

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("smartroute")

app = FastAPI(title="SmartRoute")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    """Reject huge bodies early (checks the Content-Length header)."""
    length = request.headers.get("content-length", "0")
    if length.isdigit() and int(length) > config.MAX_REQUEST_BYTES:
        return JSONResponse({"detail": "Request body too large"}, status_code=413)
    return await call_next(request)


async def require_api_key(x_api_key: str = Header(default="")) -> str:
    """Gateway-level auth: client must send X-API-Key equal to API_KEY."""
    if not config.API_KEY or not secrets.compare_digest(x_api_key, config.API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return x_api_key


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/metrics")
async def prometheus_metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/chat")
async def chat(body: ChatRequest, api_key: str = Depends(require_api_key)) -> StreamingResponse:
    """Streams the answer back as Server-Sent Events (see streaming.py)."""
    request_id = uuid.uuid4().hex[:12]
    if await is_rate_limited(api_key):
        metrics.rate_limit_total.inc()
        log.warning("request_id=%s status=rate_limited", request_id)
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please wait a moment and try again.")
    return StreamingResponse(
        stream_chat(body.message, request_id),
        media_type="text/event-stream",
        headers={"X-Request-ID": request_id, "Cache-Control": "no-cache"},
    )
