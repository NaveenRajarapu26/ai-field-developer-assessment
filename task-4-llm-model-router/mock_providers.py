
import asyncio

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel


app = FastAPI(title="Mock LLM Providers")


class CompletionRequest(BaseModel):
    prompt: str
    max_tokens: int = 256
    scenario: str = "normal"


@app.post("/primary")
async def primary_model(request: CompletionRequest):

    if request.scenario in {"primary_429", "backup_failure"}:
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded"}
        )

    if request.scenario == "primary_timeout":
        # Longer than our three-second deadline
        await asyncio.sleep(3.5)

    if request.scenario == "primary_500":
        return JSONResponse(
            status_code=500,
            content={"error": "Internal provider failure"}
        )

    return {
        "model": "primary-model",
        "completion": f"Primary response: {request.prompt}"
    }


@app.post("/backup")
async def backup_model(request: CompletionRequest):

    if request.scenario == "backup_failure":
        return JSONResponse(
            status_code=503,
            content={"error": "Backup provider unavailable"}
        )

    return {
        "model": "backup-model",
        "completion": f"Backup response: {request.prompt}"
    }
