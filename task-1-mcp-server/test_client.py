"""Small interactive demo: run with 'python test_client.py'."""

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, MCPError, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    config = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).with_name("server.py"))],
    )
    async with stdio_client(config) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("Available tools:", [tool.name for tool in tools.tools])

            for name, args in [
                ("get_customer_record", {"customer_id": "CUST-12345"}),
                ("trigger_refund", {
                    "customer_id": "CUST-12345",
                    "amount": 100.5,
                    "reason": "Customer returned the product",
                }),
                ("trigger_refund", {
                    "customer_id": "CUST-12345",
                    "amount": -50.0,
                    "reason": "Customer returned the product",
                }),
            ]:
                print(f"\nCalling {name}: {json.dumps(args)}")
                try:
                    result = await session.call_tool(name, arguments=args)
                    print("isError:", result.is_error)
                    for item in result.content:
                        if item.type == "text":
                            print(item.text)
                except MCPError as exc:
                    print(f"JSON-RPC error {exc.code}: {exc.message}")


if __name__ == "__main__":
    asyncio.run(main())
