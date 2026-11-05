"""Read actual subprocess stdout/stderr; verify JSON-RPC response framing."""

import json
import queue
import subprocess
import sys
import threading
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1] / "server.py"


def test_stdio_isolation() -> None:
    proc = subprocess.Popen(
        [sys.executable, str(SERVER)],
        cwd=str(SERVER.parent),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        bufsize=1,
    )
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    responses: queue.Queue[dict] = queue.Queue()

    def read_stdout() -> None:
        for line in proc.stdout:
            stdout_lines.append(line)
            try:
                responses.put(json.loads(line))
            except json.JSONDecodeError:
                responses.put({"_invalid_stdout": line})

    def read_stderr() -> None:
        for line in proc.stderr:
            stderr_lines.append(line)

    t1 = threading.Thread(target=read_stdout, daemon=True)
    t2 = threading.Thread(target=read_stderr, daemon=True)
    t1.start()
    t2.start()

    def send(payload: dict) -> None:
        proc.stdin.write(json.dumps(payload, allow_nan=False) + "\n")
        proc.stdin.flush()

    def expect_id(request_id: int) -> dict:
        while True:
            msg = responses.get(timeout=10)
            assert "_invalid_stdout" not in msg, f"stdout contamination: {msg}"
            assert msg.get("jsonrpc") == "2.0"
            if msg.get("id") == request_id:
                return msg

    try:
        send({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "raw-stdio-test", "version": "1.0.0"},
            },
        })
        assert "result" in expect_id(1)

        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        assert len(expect_id(2)["result"]["tools"]) == 2

        send({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "trigger_refund", "arguments": {
                "customer_id": "CUST-12345",
                "amount": -5.0,
                "reason": "Customer returned the product",
            }},
        })
        assert expect_id(3)["error"]["code"] == -32602

        send({"jsonrpc": "2.0", "id": 4, "method": "unknown/method", "params": {}})
        assert expect_id(4)["error"]["code"] == -32601
    finally:
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        t1.join(timeout=2)
        t2.join(timeout=2)
        proc.stdin.close()
        proc.stdout.close()
        proc.stderr.close()

    # Catch any stdout lines not already consumed by expect_id().
    assert stdout_lines
    for line in stdout_lines:
        data = json.loads(line)
        assert data["jsonrpc"] == "2.0"
    assert "Starting Customer MCP Server" in "".join(stderr_lines)
    assert "Invalid input for trigger_refund" in "".join(stderr_lines)
