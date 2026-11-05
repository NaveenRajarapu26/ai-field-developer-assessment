"""Real MCP client-to-server tests, including strict input edge cases."""

import asyncio
import json
import math
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, MCPError, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).resolve().parents[1] / "server.py"
REFUND = {
    "customer_id": "CUST-12345",
    "amount": 100.5,
    "reason": "Customer returned the product",
}
INVALID_CASES = [
    ("get_customer_record", {"customer_id": "12345"}),
    ("get_customer_record", {}),
    ("get_customer_record", {"customer_id": "CUST-12345", "extra": True}),
    ("get_customer_record", {"customer_id": 12345}),
    ("get_customer_record", {"customer_id": "CUST-12345\n"}),
    ("trigger_refund", {**REFUND, "amount": 0.0}),
    ("trigger_refund", {**REFUND, "amount": -10.0}),
    ("trigger_refund", {**REFUND, "amount": math.nan}),
    ("trigger_refund", {**REFUND, "amount": math.inf}),
    ("trigger_refund", {**REFUND, "amount": "100.5"}),
    ("trigger_refund", {**REFUND, "amount": 100}),
    ("trigger_refund", {"customer_id": "CUST-12345", "amount": 20.0}),
    ("trigger_refund", {**REFUND, "reason": "Bad"}),
    ("trigger_refund", {**REFUND, "reason": "           "}),
    ("trigger_refund", {**REFUND, "approved": True}),
    ("trigger_refund", {**REFUND, "amount": True}),
]


async def exercise_client() -> None:
    config = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
    async with stdio_client(config) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert {tool.name for tool in tools.tools} == {
                "get_customer_record", "trigger_refund"
            }

            for name, args in INVALID_CASES:
                with pytest.raises(MCPError) as captured:
                    await session.call_tool(name, arguments=args)
                assert captured.value.code == -32602, (name, args)

            with pytest.raises(MCPError) as captured:
                await session.call_tool("tool_does_not_exist", arguments={})
            assert captured.value.code == -32602

            lookup = await session.call_tool(
                "get_customer_record", arguments={"customer_id": "CUST-12345"}
            )
            assert not lookup.is_error
            assert json.loads(lookup.content[0].text)["name"] == "John"

            refund = await session.call_tool("trigger_refund", arguments=REFUND)
            assert not refund.is_error
            data = json.loads(refund.content[0].text)
            assert data["status"] == "simulated"
            assert data["amount"] == 100.5

            missing = await session.call_tool(
                "get_customer_record", arguments={"customer_id": "CUST-99999"}
            )
            assert missing.is_error

            missing_refund = await session.call_tool(
                "trigger_refund", arguments={**REFUND, "customer_id": "CUST-99999"}
            )
            assert missing_refund.is_error


def test_tools_over_real_stdio() -> None:
    asyncio.run(exercise_client())
