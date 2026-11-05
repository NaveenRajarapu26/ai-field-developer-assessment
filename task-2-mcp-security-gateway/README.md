# MCP Security Gateway

This gateway checks who is calling before forwarding a JSON-RPC request to the mock MCP server. The rule is simple: a tool whose name starts with `admin_` requires the `admin` role.

It uses FastAPI for the HTTP endpoint and HTTPX to call the downstream server. Roles come from the token mapping in `auth.py`, rather than anything supplied in the request body.

## Run it

From this task folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On macOS or Linux, activate the environment with `source .venv/bin/activate`.

Start the mock server:

```powershell
python -m uvicorn mock_server:app --host 127.0.0.1 --port 8001
```

Open a second terminal in the same folder, activate the environment, and start the gateway:

```powershell
python -m uvicorn gateway:app --host 127.0.0.1 --port 8000
```

Send requests to `POST http://127.0.0.1:8000/mcp`.

## Try the authorization rule

The demo has two tokens:

| Bearer token | Role |
| --- | --- |
| `demo-admin-token` | admin |
| `demo-viewer-token` | viewer |

For example, this PowerShell request tries to call an admin tool as a viewer:

```powershell
$headers = @{ Authorization = "Bearer demo-viewer-token" }
$body = '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"admin_reset_key","arguments":{}}}'
Invoke-RestMethod -Uri http://127.0.0.1:8000/mcp -Method Post -Headers $headers -ContentType application/json -Body $body
```

The response contains error code `-32001` and the message `Unauthorized Tool Call`. The gateway returns this before making any downstream request. Change the token to `demo-admin-token` to allow the call.

## Request handling

| Request | What happens |
| --- | --- |
| Authenticated `tools/list` | Forwarded with the original request body |
| Regular tool call from an authenticated user | Forwarded |
| `admin_*` tool call from an admin | Forwarded |
| `admin_*` tool call from a viewer | JSON-RPC error `-32001` |
| Missing or invalid token | HTTP 401 |
| Malformed JSON | JSON-RPC error `-32700` |
| Invalid request structure | JSON-RPC error `-32600` |

Allowed requests keep the downstream response body and HTTP status. Downstream timeouts and connection failures return controlled errors without exposing internal connection details.

## Tests

```powershell
python -m pytest -v
```

The tests cover authentication, request validation, forwarding, and timeout handling. They also check that a blocked admin call makes zero downstream requests.

`auth.py` handles tokens, `gateway.py` handles validation and forwarding, and `mock_server.py` supplies the downstream tools. The tests are in `tests/test_gateway.py`.

## Scope

The fixed tokens are for the local demo. A deployed service would need a proper source of identity and access tokens.

This proxy handles the assessment's HTTP/JSON-RPC flow. It rejects batch requests and does not implement full MCP Streamable HTTP sessions or SSE forwarding. The downstream server only simulates tool execution.
