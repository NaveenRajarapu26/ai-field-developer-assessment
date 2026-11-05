
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock MCP Server")


@app.post("/mcp")
async def handle_mcp(request: Request):
    payload = await request.json()

    method = payload.get("method")
    request_id = payload.get("id")

    # Tool discovery
    if method == "tools/list":
        result = {
            "tools": [
                {
                    "name": "get_customer_record",
                    "description": "Get customer information",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "customer_id": {"type": "string"}
                        }
                    }
                },
                {
                    "name": "admin_reset_key",
                    "description": "Simulate an admin key reset",
                    "inputSchema": {
                        "type": "object",
                        "properties": {}
                    }
                }
            ]
        }

    # Tool execution
    elif method == "tools/call":
        tool_name = payload.get("params", {}).get("name")

        result = {
            "content": [
                {
                    "type": "text",
                    "text": f"Executed tool: {tool_name}"
                }
            ],
            "isError": False
        }

    else:
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32601,
                "message": "Method not found"
            }
        })

    return JSONResponse({
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result
    })
