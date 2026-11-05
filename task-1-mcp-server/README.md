# Customer Service MCP Server

This server exposes two tools through the official Python `mcp` SDK: one to look up a customer and one to simulate a refund. It uses Pydantic for input validation and stdio for communication with the client.

The sample customers are `CUST-12345` and `CUST-67890`. Records are kept in memory, and refunds do not move money or change balances.

## Run it

From this task folder, create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On macOS or Linux, activate it with `source .venv/bin/activate` instead. The project was tested with Python 3.12 and the MCP SDK v2 API.

Try the client and run the tests:

```powershell
python test_client.py
python -m pytest -v
```

The client starts the server as a subprocess and handles the MCP handshake. Running `python server.py` directly also starts the server, but it will wait for JSON-RPC messages on stdin.

## Tools and validation

| Tool | Inputs | Result |
| --- | --- | --- |
| `get_customer_record` | `customer_id` | Customer details from the sample records |
| `trigger_refund` | `customer_id`, `amount`, `reason` | A simulated refund confirmation |

The input rules are defined in `models.py`:

- `customer_id` must be `CUST-` followed by exactly five ASCII digits.
- `amount` must be a positive, finite float. This implementation accepts `100.0` but rejects integer `100`, strings, and booleans.
- `reason` must have at least 10 characters after trimming surrounding whitespace.
- Missing fields and extra fields are rejected.

The integer rule is a strict interpretation of the assessment's float requirement. JSON Schema calls both `100` and `100.0` numbers, so a separate validator enforces the distinction. For a real payment service, amounts would need a representation such as integer minor units or `Decimal`.

Here are two `tools/call` parameter examples. The client adds the JSON-RPC envelope:

```json
{"name":"get_customer_record","arguments":{"customer_id":"CUST-12345"}}
```

```json
{"name":"trigger_refund","arguments":{"customer_id":"CUST-12345","amount":100.5,"reason":"Customer returned the product"}}
```

Invalid arguments and unknown tool names return JSON-RPC `-32602`. Unknown JSON-RPC methods return `-32601`. A correctly formatted ID that has no matching customer returns a tool result with `isError: true` and a message explaining what happened.

## Keeping stdout clean

The MCP SDK writes JSON-RPC messages to stdout. Application logs use Python's `logging` module, which writes to stderr. There are no `print()` calls in the server; the demo client's prints come from a separate process.

`tests/test_stdio.py` checks the raw subprocess output, the handshake, tool calls, and error responses. `tests/test_tools.py` uses an MCP client to check discovery, valid calls, invalid inputs, and missing customers.

## Where things live

- `server.py`: tool registration, request handling, and stdio transport
- `models.py`: input validation
- `services.py`: sample customer records and refund simulation
- `test_client.py`: runnable client demo
- `tests/`: tool and transport tests

The low-level SDK server lets the handlers return the required JSON-RPC validation errors directly. Customer logic is kept separate from transport handling to make both easier to follow.

## References

- [Official Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP tools specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- [SDK low-level server guide](https://py.sdk.modelcontextprotocol.io/advanced/low-level-server/)
