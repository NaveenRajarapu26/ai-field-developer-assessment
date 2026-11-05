
import asyncio
import json
import time

import httpx


async def main():
    url = "http://127.0.0.1:8000/generate"

    first_chunk_time = None
    chunk_count = 0
    total_chars = 0

    start = time.perf_counter()

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

                payload = line[5:].strip()

                if payload == "[DONE]":
                    break

                event = json.loads(payload)
                content = event["choices"][0]["delta"]["content"]

                if first_chunk_time is None:
                    first_chunk_time = time.perf_counter()

                chunk_count += 1
                total_chars += len(content)

    end = time.perf_counter()

    print("\n=== STREAMING PERFORMANCE ===")
    print(
        f"Time to first safe output: "
        f"{(first_chunk_time - start) * 1000:.2f} ms"
        if first_chunk_time is not None
        else "No output received"
    )
    print(f"Total duration: {(end - start) * 1000:.2f} ms")
    print(f"Safe output chunks: {chunk_count}")
    print(f"Total output characters: {total_chars}")

    assert first_chunk_time is not None
    assert first_chunk_time < end

    print("\nPASS: Safe output was received through streaming")


if __name__ == "__main__":
    asyncio.run(main())
