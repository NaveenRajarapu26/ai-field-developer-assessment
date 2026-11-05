
import asyncio
import json

import httpx
import pytest

import gateway


SAMPLE_CHUNKS = [
    "Hello! Here are the customer details. ",
    "Email: john",
    ".smith@",
    "gmail.com. ",
    "SSN: 123-",
    "45-6789. ",
    "Card: 4111 ",
    "1111 1111 ",
    "1111. ",
    "Thank you!"
]


def make_provider_stream(chunks):
    """Create realistic SSE events from provider text chunks."""
    events = []

    for chunk in chunks:
        event = {
            "choices": [
                {"delta": {"content": chunk}}
            ]
        }
        events.append(f"data: {json.dumps(event)}\n\n")

    events.append("data: [DONE]\n\n")
    return "".join(events).encode("utf-8")


async def collect_gateway_events():
    events = []

    async for event in gateway.stream_safe_response("Test prompt"):
        events.append(event)

    return events


def configure_mock_provider(monkeypatch, response):
    """Replace upstream HTTP calls with a controlled mock."""
    original_client = httpx.AsyncClient

    def handler(request):
        assert request.method == "POST"
        return response

    transport = httpx.MockTransport(handler)

    def mock_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(gateway.httpx, "AsyncClient", mock_client)


def extract_text(events):
    text = ""

    for event in events:
        if not event.startswith("data:"):
            continue

        payload = event[5:].strip()

        if payload == "[DONE]":
            continue

        data = json.loads(payload)
        text += data["choices"][0]["delta"]["content"]

    return text


# 1. Complete streaming redaction
def test_gateway_redacts_provider_stream(monkeypatch):
    provider_data = make_provider_stream(SAMPLE_CHUNKS)

    configure_mock_provider(
        monkeypatch,
        httpx.Response(
            200,
            content=provider_data,
            headers={"content-type": "text/event-stream"}
        )
    )

    events = asyncio.run(collect_gateway_events())
    output = extract_text(events)

    assert "john.smith@gmail.com" not in output
    assert "123-45-6789" not in output
    assert "4111 1111 1111 1111" not in output

    assert output.count("[REDACTED]") == 3
    assert events[-1] == "data: [DONE]\n\n"


# 2. Provider failure should not look like success
def test_provider_http_failure(monkeypatch):
    configure_mock_provider(
        monkeypatch,
        httpx.Response(503, text="Private upstream failure")
    )

    events = asyncio.run(collect_gateway_events())
    combined = "".join(events)

    assert "event: error" in combined
    assert "Private upstream failure" not in combined
    assert "data: [DONE]" not in combined


# 3. Malformed provider events should not leak content
def test_malformed_provider_event(monkeypatch):
    provider_data = (
        'data: {"invalid": "structure"}\n\n'
        'data: {"choices": [{"delta": {"content": "Hello!"}}]}\n\n'
        'data: [DONE]\n\n'
    ).encode("utf-8")

    configure_mock_provider(
        monkeypatch,
        httpx.Response(200, content=provider_data)
    )

    events = asyncio.run(collect_gateway_events())
    output = extract_text(events)

    assert output == "Hello!"
    assert events[-1] == "data: [DONE]\n\n"


# 4. Different provider chunk sizes
@pytest.mark.parametrize("chunk_size", [1, 3, 8, 32])
def test_gateway_chunk_boundaries(monkeypatch, chunk_size):
    text = (
        "Email: john.smith@gmail.com. "
        "SSN: 123-45-6789."
    )

    chunks = [
        text[i:i + chunk_size]
        for i in range(0, len(text), chunk_size)
    ]

    configure_mock_provider(
        monkeypatch,
        httpx.Response(
            200,
            content=make_provider_stream(chunks)
        )
    )

    events = asyncio.run(collect_gateway_events())
    output = extract_text(events)

    assert output == (
        "Email: [REDACTED]. "
        "SSN: [REDACTED]."
    )


def test_oversized_unterminated_line(monkeypatch):
    configure_mock_provider(monkeypatch, httpx.Response(
        200, content=b"data: " + b"x" * (gateway.MAX_EVENT_BYTES + 1)
    ))
    events = asyncio.run(collect_gateway_events())
    assert len(events) == 1
    assert events[0].startswith("event: error")


def test_first_safe_delta_arrives_before_provider_finishes(monkeypatch):
    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield make_provider_stream(["Hello! "]).split(b"data: [DONE]")[0]
            await asyncio.sleep(10)
            yield b"data: [DONE]\n\n"

    configure_mock_provider(monkeypatch, httpx.Response(200, stream=SlowStream()))

    async def first_event():
        stream = gateway.stream_safe_response("Test")
        try:
            event = await asyncio.wait_for(anext(stream), timeout=1)
            assert extract_text([event]) == "Hello! "
        finally:
            await stream.aclose()

    asyncio.run(first_event())
