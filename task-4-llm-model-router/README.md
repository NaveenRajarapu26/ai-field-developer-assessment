# Token Rate Limiter and Model Fallback

This gateway gives each tenant a budget of 50,000 reserved tokens over a rolling 60-second window. It stores reservations in an on-disk SQLite database and sends accepted requests to the primary model provider.

If the primary returns HTTP 429 or takes longer than three seconds, the gateway tries the backup provider. Both providers are local mocks, so the failure paths can be tried without external API keys.

## Run it

Use Python 3.11 or newer; the project was tested with Python 3.12. From this task folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On macOS or Linux, activate the environment with `source .venv/bin/activate`. SQLite comes with Python, so there is no separate database service to install.

Start the mock providers:

```powershell
python -m uvicorn mock_providers:app --host 127.0.0.1 --port 8001
```

In a second terminal, activate the same environment and start the gateway:

```powershell
python -m uvicorn gateway:app --host 127.0.0.1 --port 8000
```

## Send a request

```powershell
$headers = @{ "X-API-Key" = "demo-key-tenant-a" }
$body = '{"prompt":"Explain MCP simply","max_tokens":500,"scenario":"normal"}'
Invoke-RestMethod -Uri http://127.0.0.1:8000/completions -Method Post -Headers $headers -ContentType application/json -Body $body
```

The other demo key is `demo-key-tenant-b`. Each key maps to a separate tenant budget.

Change `scenario` to try the different paths:

| Scenario | Expected behavior |
| --- | --- |
| `normal` | Return the primary response |
| `primary_429` | Use the backup after the primary returns 429 |
| `primary_timeout` | Use the backup after the three-second deadline |
| `primary_500` | Return a sanitized error without fallback |
| `backup_failure` | Primary returns 429, then backup returns 503 |

## Token reservations

Before calling a provider, the gateway reserves the UTF-8 byte length of the prompt plus `max_tokens`. For byte-based tokenizers, this intentionally overestimates input usage. The same `max_tokens` value is forwarded to the provider.

Reservations are stored in `rate_limits.db`. The limiter uses `BEGIN IMMEDIATE` to acquire the SQLite write lock before checking usage and inserting a reservation. That keeps two concurrent requests from both claiming the same remaining budget. Expired rows are removed when a reservation is checked.

A request that would exceed the tenant's current budget gets HTTP 429 with a `Retry-After` header. If its budget is larger than the entire window limit, it gets HTTP 422: waiting cannot make that request fit.

This tracks reserved budgets, not actual provider usage. Unused output tokens and failed requests are not refunded. Exact accounting would need the provider's tokenizer and a way to reconcile reported usage.

## Deadlines and errors

The primary request has a three-second total deadline enforced by `asyncio.timeout()`. The backup gets a separate five-second deadline. SQLite reservations run in a worker thread so database waits do not block the async event loop.

Fallback is limited to primary 429 responses and timeouts, as requested in the assessment. Other failures return a controlled gateway error, for example:

```json
{
  "error": {
    "code": "UPSTREAM_ERROR",
    "message": "Primary model provider failed"
  }
}
```

Validation failures use the same error envelope. Upstream response bodies and stack traces are not returned to clients.

## Tests

```powershell
python -m pytest -v
```

The suite checks expiration, tenant isolation, concurrent reservations, fallback, deadline cancellation, input validation, and error responses. Each database test uses its own temporary SQLite file.

The concurrency test submits ten reservations of 10,000 tokens against a 50,000-token limit. Exactly five should be accepted.

For manual examples, `limiter_demo.py` exercises the limiter and `router_demo.py` exercises provider routing.

## Where things live

- `gateway.py`: request validation, tenant lookup, and token reservation
- `rate_limiter.py`: sliding-window admission checks
- `database.py`: SQLite setup and connections
- `model_router.py`: provider calls, deadlines, and fallback
- `mock_providers.py`: local success and failure scenarios

The fixed API keys and simplified provider responses keep the demo easy to run. SQLite serializes writes, which is useful for correctness here but would need further consideration under heavy traffic.
