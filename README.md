# AI Field Developer Assessment

This repository contains my solutions to the four assessment tasks. Each task is a separate Python project with its own dependencies, tests, and instructions.

The demos use local mock servers, so you can run them without a paid API key. Task 3 also has an optional configuration for an OpenAI-compatible provider.

| Task | Project | What it does |
| --- | --- | --- |
| 1 | [Custom MCP server](task-1-mcp-server/README.md) | Looks up customers and simulates refunds over stdio, with strict input validation |
| 2 | [MCP security gateway](task-2-mcp-security-gateway/README.md) | Checks Bearer tokens and blocks admin tool calls from viewers |
| 3 | [Streaming PII guardrail](task-3-llm-streaming-guardrail/README.md) | Redacts emails, SSNs, and card numbers from streamed responses |
| 4 | [Rate limiter and model fallback](task-4-llm-model-router/README.md) | Stores token reservations in SQLite and switches providers on a 429 or timeout |

## Getting started

Python 3.12 is the tested version. Task 4 needs Python 3.11 or newer because it uses `asyncio.timeout()`.

Open a terminal in the task you want to run, then create its virtual environment. For example, in PowerShell:

```powershell
cd task-1-mcp-server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -v
```

On macOS or Linux, use `source .venv/bin/activate` to activate the environment. The other commands are the same.

Repeat these steps in the other task folders as needed. Run tests from each task folder: the projects reuse module names such as `gateway`, so they should be tested separately.

Each task's README explains how to start its servers and try the demo. Tasks 2, 3, and 4 use ports 8000 and 8001 by default, so run one at a time.

## A few choices to be aware of

- Refunds in Task 1 are simulated; no payment is processed.
- Tokens and tenant API keys in the demos are fixed local credentials.
- Task 3 buffers unfinished text candidates so PII split across chunks is not released early. Detection covers common formats, with details in its README.
- Task 4 limits reserved token budgets rather than reconciling actual provider usage.

The task READMEs explain these choices alongside the code and test instructions.
