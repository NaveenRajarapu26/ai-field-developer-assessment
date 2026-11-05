
import asyncio

from model_router import (
    GatewayError,
    route_completion
)


async def main():

    scenarios = [
        ("Normal request", "normal", "primary"),
        ("Primary HTTP 429", "primary_429", "backup"),
        ("Primary timeout", "primary_timeout", "backup")
    ]

    for label, scenario, expected_provider in scenarios:

        print(f"\nTEST: {label}")

        try:
            result = await route_completion({
                "prompt": "Explain MCP simply",
                "scenario": scenario
            })

            print("Provider:", result["provider"])
            print("Response:", result["result"]["completion"])

            assert result["provider"] == expected_provider

            print("PASS")

        except GatewayError as error:
            print("Gateway error:", error.code)
            raise

    # Primary 500 should return a sanitized error,
    # not trigger backup.
    print("\nTEST: Primary HTTP 500")

    try:
        await route_completion({
            "prompt": "Explain MCP simply",
            "scenario": "primary_500"
        })
        raise AssertionError("Expected an upstream error")

    except GatewayError as error:
        assert error.code == "UPSTREAM_ERROR"
        assert error.message == "Primary model provider failed"
        print("PASS: Sanitized gateway error")

    print("\nALL ROUTER DEMO TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
