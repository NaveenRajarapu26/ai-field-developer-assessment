
import asyncio
import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel


app = FastAPI(title="Mock LLM Provider")


class GenerateRequest(BaseModel):
    prompt: str


async def generate_chunks(prompt: str):
    # Simulate text arriving from a real LLM
    chunks = [
        "Hello! Here are the customer details. ",
        "Email: john",
        ".smith@",
        "gmail.com. ",
        "SSN: 123-",
        "45-6789. ",
        "Card: 4111 ",
        "1111 1111 ",
        "1111. ",
        "Thank you!"
    ]

    for chunk in chunks:
        await asyncio.sleep(0.1)

        event = {
            "choices": [
                {
                    "delta": {
                        "content": chunk
                    }
                }
            ]
        }

        yield f"data: {json.dumps(event)}\n\n"

    yield "data: [DONE]\n\n"


@app.post("/generate")
async def generate(request: GenerateRequest):
    return StreamingResponse(
        generate_chunks(request.prompt),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )
