
import json
import logging

import httpx

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.exceptions import HTTPException

from auth import get_user_role


app = FastAPI(title="MCP Security Gateway")

DOWNSTREAM_URL = "http://127.0.0.1:8001/mcp"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-gateway")


def rpc_error(request_id, code, message):
    """Return a standard JSON-RPC error response."""

    return JSONResponse({
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message
        }
    })


@app.post("/mcp")
async def mcp_gateway(request: Request):

    # 1. Authenticate the caller
    try:
        role = get_user_role(
            request.headers.get("authorization")
        )
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32001,
                    "message": "Authentication failed"
                }
            },
            headers={"WWW-Authenticate": "Bearer"}
        )

    # 2. Parse the incoming JSON-RPC request
    raw_body = await request.body()

    try:
        payload = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError):
        return rpc_error(None, -32700, "Parse error")

    # Reject batch requests to prevent authorization bypass
    if not isinstance(payload, dict):
        return rpc_error(None, -32600, "Invalid Request")

    request_id = payload.get("id")

    if request_id is not None and type(request_id) not in (str, int, float):
        return rpc_error(None, -32600, "Invalid Request")

    # Check basic JSON-RPC structure
    if (
        payload.get("jsonrpc") != "2.0"
        or not isinstance(payload.get("method"), str)
        or not payload["method"]
    ):
        return rpc_error(
            request_id,
            -32600,
            "Invalid Request"
        )

    method = payload["method"]

    if "params" in payload and not isinstance(payload["params"], (dict, list)):
        return rpc_error(request_id, -32602, "Invalid params")

    # 3. Apply tool-level authorization
    if method == "tools/call":

        params = payload.get("params")

        if not isinstance(params, dict):
            return rpc_error(
                request_id,
                -32602,
                "Invalid params"
            )

        tool_name = params.get("name")

        if not isinstance(tool_name, str) or not tool_name:
            return rpc_error(
                request_id,
                -32602,
                "Invalid tool name"
            )

        # Admin tools require admin role
        if tool_name.startswith("admin_") and role != "admin":

            logger.warning(
                "Blocked admin tool call for role %s",
                role
            )

            return rpc_error(
                request_id,
                -32001,
                "Unauthorized Tool Call"
            )

    # 4. Forward authorized requests downstream
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            upstream = await client.post(
                DOWNSTREAM_URL,
                content=raw_body,
                headers={
                    "Content-Type": "application/json"
                }
            )

        logger.info(
            "Forwarded method=%s role=%s",
            method,
            role
        )

        # Preserve downstream status, body and content type.
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get(
                "content-type",
                "application/json"
            )
        )

    except httpx.TimeoutException:
        logger.error("Downstream MCP server timed out")

        return rpc_error(
            request_id,
            -32002,
            "Downstream server timeout"
        )

    except httpx.RequestError:
        logger.error("Downstream MCP server unavailable")

        return rpc_error(
            request_id,
            -32002,
            "Downstream server unavailable"
        )
