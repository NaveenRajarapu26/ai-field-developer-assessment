
import asyncio
import json

import httpx


async def main():

    url = "http://127.0.0.1:8000/generate"

    print("=== LLM GATEWAY STREAMING TEST ===")

    complete_response = ""

    async with httpx.AsyncClient(timeout=30.0) as client:

        async with client.stream(
            "POST",
            url,
            json={"prompt": "Show customer details"}
        ) as response:

            response.raise_for_status()

            async for line in response.aiter_lines():

                if not line.startswith("data:"):
                    continue

                data = line[5:].strip()

                if data == "[DONE]":
                    print("\nStream completed")
                    break

                event = json.loads(data)

                text = event["choices"][0]["delta"]["content"]

                complete_response += text

                print(text, end="", flush=True)

    print("\n\n=== VALIDATION ===")

    assert "john.smith@gmail.com" not in complete_response
    assert "123-45-6789" not in complete_response
    assert "4111 1111 1111 1111" not in complete_response

    assert complete_response.count("[REDACTED]") == 3

    print("PASS: Email redacted")
    print("PASS: SSN redacted")
    print("PASS: Credit card redacted")
    print("PASS: All sensitive information removed")


if __name__ == "__main__":
    asyncio.run(main())
