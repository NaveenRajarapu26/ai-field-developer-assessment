
import asyncio
import math
import logging

from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from typing import Literal

from rate_limiter import TokenRateLimiter
from model_router import GatewayError, route_completion


# 1. Create the gateway
app = FastAPI(title="LLM Rate Limiting and Fallback Gateway")

logger = logging.getLogger("llm-gateway")

limiter = TokenRateLimiter(
    limit=50_000,
    window=60
)


# 2. Demo tenant credentials
# Production systems should use proper API key validation.
TENANT_KEYS = {
    "demo-key-tenant-a": "tenant-a",
    "demo-key-tenant-b": "tenant-b",
}


# 3. Request schema
class CompletionRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=10000)
    max_tokens: int = Field(default=256, strict=True, ge=1, le=50000)
    scenario: Literal[
        "normal",
        "primary_429",
        "primary_timeout",
        "primary_500",
        "backup_failure"
    ] = "normal"


# 4. Standardized gateway errors
def gateway_error(status_code, code, message, headers=None):
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "error": {
                "code": code,
                "message": message
            }
        }
    )


@app.exception_handler(RequestValidationError)
async def invalid_request(_request, _error):
    return gateway_error(422, "INVALID_REQUEST", "Invalid completion request")


# 5. Estimate token reservation
def estimate_tokens(prompt: str, max_tokens: int) -> int:
    """
    Approximate input tokens plus maximum output tokens.

    Reserve a UTF-8 byte upper bound for byte-based tokenizers.
    This intentionally overcounts; exact accounting needs the provider tokenizer.
    """
    input_estimate = len(prompt.encode("utf-8"))

    return input_estimate + max_tokens


# 6. Main completion endpoint
@app.post("/completions")
async def completions(
    request: CompletionRequest,
    x_api_key: str | None = Header(default=None)
):

    # Authenticate tenant
    tenant = TENANT_KEYS.get(x_api_key)

    if tenant is None:
        return gateway_error(
            401,
            "INVALID_API_KEY",
            "Invalid or missing API key"
        )

    # Calculate requested token budget
    tokens = estimate_tokens(
        request.prompt,
        request.max_tokens
    )

    if tokens > limiter.limit:
        return gateway_error(
            422, "TOKEN_BUDGET_TOO_LARGE",
            "Requested token budget exceeds the tenant window limit"
        )

    # Atomically reserve tokens using SQLite
    try:
        rate_result = await asyncio.to_thread(
            limiter.reserve,
            tenant,
            tokens
        )
    except Exception:
        logger.exception("Rate limiter failed")

        return gateway_error(
            503,
            "RATE_LIMITER_UNAVAILABLE",
            "Unable to process the request"
        )

    # Reject requests exceeding tenant quota
    if not rate_result.allowed:
        retry_seconds = max(
            1,
            math.ceil(rate_result.retry_after)
        )

        return gateway_error(
            429,
            "RATE_LIMIT_EXCEEDED",
            "Tenant token limit exceeded",
            headers={"Retry-After": str(retry_seconds)}
        )

    # Forward accepted request to the model router
    try:
        result = await route_completion({
            "prompt": request.prompt,
            "max_tokens": request.max_tokens,
            "scenario": request.scenario
        })

        return {
            "provider": result["provider"],
            "result": result["result"],
            "usage": {
                "reserved_tokens": tokens,
                "remaining_tokens": rate_result.remaining_tokens
            }
        }

    except GatewayError as error:
        logger.warning(
            "Model routing failed: %s",
            error.code
        )

        return gateway_error(
            error.status_code,
            error.code,
            error.message
        )
