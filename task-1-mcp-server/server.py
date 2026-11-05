"""Two-tool MCP server. Standard output is exclusively for STDIO JSON-RPC."""

import asyncio
import json
import logging

from mcp import MCPError
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    INVALID_PARAMS,
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)
from pydantic import ValidationError

from models import CustomerInput, RefundInput
from services import get_customer_record, trigger_refund


# logging.StreamHandler writes to stderr by default; never print in the server.
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("customer-mcp")


async def list_tools(
    ctx: ServerRequestContext,
    params: PaginatedRequestParams | None,
) -> ListToolsResult:
    return ListToolsResult(
        tools=[
            Tool(
                name="get_customer_record",
                description="Look up a customer using a CUST-XXXXX identifier",
                input_schema=CustomerInput.model_json_schema(),
            ),
            Tool(
                name="trigger_refund",
                description="Validate and simulate a customer refund (no money is transferred)",
                input_schema=RefundInput.model_json_schema(),
            ),
        ]
    )


def tool_result(payload: dict, *, is_error: bool = False) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload, indent=2))],
        is_error=is_error,
    )


async def call_tool(
    ctx: ServerRequestContext,
    params: CallToolRequestParams,
) -> CallToolResult:
    models = {
        "get_customer_record": CustomerInput,
        "trigger_refund": RefundInput,
    }
    model = models.get(params.name)
    if model is None:
        # MCP tools spec treats unknown tool names as invalid tools/call params.
        raise MCPError(INVALID_PARAMS, f"Unknown tool: {params.name}")

    try:
        data = model.model_validate(
            params.arguments if params.arguments is not None else {}
        )
    except ValidationError as exc:
        logger.warning("Invalid input for %s", params.name)
        raise MCPError(
            INVALID_PARAMS,
            "Invalid tool parameters",
            data={"errors": exc.errors(include_context=False, include_input=False)},
        ) from exc

    if params.name == "get_customer_record":
        result = get_customer_record(data.customer_id)
        if result is None:
            return tool_result({"message": "Customer not found"}, is_error=True)
        logger.info("Customer lookup completed")
        return tool_result(result)

    result = trigger_refund(data.customer_id, data.amount, data.reason)
    if result is None:
        return tool_result({"message": "Customer not found; refund not simulated"}, is_error=True)
    logger.info("Refund simulation completed")
    return tool_result(result)


server = Server(
    "customer-service-mcp",
    on_list_tools=list_tools,
    on_call_tool=call_tool,
)


async def main() -> None:
    logger.info("Starting Customer MCP Server")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
