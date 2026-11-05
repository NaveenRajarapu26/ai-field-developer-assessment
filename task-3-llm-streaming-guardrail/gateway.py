
import json
import logging
import os

import httpx

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from redactor import StreamingRedactor


# 1. Create gateway
app = FastAPI(title="LLM Streaming PII Gateway")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm-gateway")

MAX_EVENT_BYTES = 65536


async def bounded_lines(response):
    """Bound the line buffer before decoding untrusted provider SSE."""
    pending = b""
    async for chunk in response.aiter_bytes():
        pending += chunk
        while b"\n" in pending:
            line, pending = pending.split(b"\n", 1)
            if len(line) > MAX_EVENT_BYTES:
                raise ValueError("SSE line exceeds size limit")
            yield line.rstrip(b"\r").decode("utf-8")
        if len(pending) > MAX_EVENT_BYTES:
            raise ValueError("SSE line exceeds size limit")
    if pending:
        yield pending.rstrip(b"\r").decode("utf-8")


# 2. Request model
class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)


# 3. Format sanitized SSE events
def make_sse_event(text: str) -> str:

    event = {
        "choices": [
            {
                "delta": {
                    "content": text
                }
            }
        ]
    }

    return f"data: {json.dumps(event)}\n\n"


# 4. Select LLM provider
def provider_settings(prompt: str):

    mode = os.getenv(
        "PROVIDER_MODE",
        "mock"
    ).lower()

    # Local mock LLM provider
    if mode == "mock":

        url = os.getenv(
            "PROVIDER_URL",
            "http://127.0.0.1:8001/generate"
        )

        body = {
            "prompt": prompt
        }

        headers = {
            "Accept": "text/event-stream"
        }

        return url, body, headers

    # Optional real OpenAI-compatible provider
    if mode == "openai_compatible":

        api_key = os.getenv("LLM_API_KEY")

        if not api_key:
            raise ValueError(
                "Provider API key is not configured"
            )

        base_url = os.getenv(
            "LLM_BASE_URL",
            "https://api.openai.com/v1"
        ).rstrip("/")

        model = os.getenv("LLM_MODEL")

        if not model:
            raise ValueError(
                "Provider model is not configured"
            )

        url = base_url + "/chat/completions"

        body = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "stream": True
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "text/event-stream"
        }

        return url, body, headers

    raise ValueError("Unsupported provider mode")


# 5. Stream and sanitize LLM output
async def stream_safe_response(prompt: str):

    redactor = StreamingRedactor()
    saw_done = False

    try:

        url, body, headers = provider_settings(prompt)

        timeout = httpx.Timeout(
            30.0,
            connect=5.0
        )

        async with httpx.AsyncClient(
            timeout=timeout
        ) as client:

            async with client.stream(
                "POST",
                url,
                json=body,
                headers=headers
            ) as response:

                response.raise_for_status()

                data_lines = []
                data_bytes = 0

                # Read SSE events incrementally
                async for line in bounded_lines(response):

                    if line.startswith("data:"):

                        part = line[5:].lstrip(" ")

                        data_bytes += len(
                            part.encode("utf-8")
                        ) + 1  # Include separators so empty data lines are bounded.

                        if data_bytes > MAX_EVENT_BYTES:
                            raise ValueError(
                                "SSE event exceeds size limit"
                            )

                        data_lines.append(part)
                        continue

                    # Ignore SSE metadata and comments
                    if line:
                        continue

                    if not data_lines:
                        continue

                    payload = "\n".join(data_lines)

                    data_lines = []
                    data_bytes = 0

                    # Provider finished streaming
                    if payload == "[DONE]":
                        saw_done = True
                        break

                    # Parse JSON event
                    try:
                        event = json.loads(payload)

                    except ValueError:
                        raise ValueError(
                            "Malformed provider SSE JSON"
                        ) from None

                    try:
                        content = (
                            event["choices"][0]["delta"]
                            .get("content")
                        )

                    except (
                        KeyError,
                        IndexError,
                        TypeError,
                        AttributeError
                    ):
                        # Ignore unrelated provider events
                        continue

                    if content is None:
                        continue

                    if not isinstance(content, str):
                        raise ValueError(
                            "Invalid provider delta"
                        )

                    # Redact before returning text
                    safe_text = redactor.feed(content)

                    if safe_text:
                        yield make_sse_event(safe_text)

        # Detect incomplete provider streams
        if not saw_done:
            raise ValueError(
                "Provider stream ended without [DONE]"
            )

        # Flush remaining safe text
        remainder = redactor.flush()

        if remainder:
            yield make_sse_event(remainder)

        yield "data: [DONE]\n\n"

    except (httpx.HTTPError, ValueError):

        logger.warning(
            "Provider stream failed",
            exc_info=False
        )

        # Never expose upstream errors to the client
        # or flush an incomplete PII candidate.
        yield (
            "event: error\n"
            'data: {"error":"Upstream streaming failed"}\n\n'
        )


# 6. API endpoint
@app.post("/generate")
async def generate(request: GenerateRequest):

    return StreamingResponse(
        stream_safe_response(request.prompt),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )
