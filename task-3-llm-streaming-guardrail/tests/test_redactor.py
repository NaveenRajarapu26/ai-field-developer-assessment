
import pytest

from redactor import StreamingRedactor


SAMPLE_TEXT = (
    "Hello! Here are the customer details. "
    "Email: john.smith@gmail.com. "
    "SSN: 123-45-6789. "
    "Card: 4111 1111 1111 1111. "
    "Thank you!"
)

EXPECTED_TEXT = (
    "Hello! Here are the customer details. "
    "Email: [REDACTED]. "
    "SSN: [REDACTED]. "
    "Card: [REDACTED]. "
    "Thank you!"
)


def process_chunks(chunks):
    """Pass chunks through the redactor and collect safe output."""
    redactor = StreamingRedactor()
    output = []

    for chunk in chunks:
        output.append(redactor.feed(chunk))

    output.append(redactor.flush())

    return "".join(output)


# 1. Check the example from our mock LLM
def test_sample_pii_redaction():
    chunks = [
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

    assert process_chunks(chunks) == EXPECTED_TEXT


# 2. Test different chunk sizes
@pytest.mark.parametrize("chunk_size", [1, 2, 3, 5, 7, 16, 64])
def test_different_chunk_boundaries(chunk_size):
    chunks = [
        SAMPLE_TEXT[i:i + chunk_size]
        for i in range(0, len(SAMPLE_TEXT), chunk_size)
    ]

    assert process_chunks(chunks) == EXPECTED_TEXT


# 3. Test each PII pattern separately
@pytest.mark.parametrize(
    "text, expected",
    [
        (
            "Contact support@example.com for help.",
            "Contact [REDACTED] for help."
        ),
        (
            "SSN: 123-45-6789.",
            "SSN: [REDACTED]."
        ),
        (
            "Card: 4111 1111 1111 1111.",
            "Card: [REDACTED]."
        )
    ]
)
def test_individual_pii_patterns(text, expected):
    chunks = list(text)  # One character at a time
    assert process_chunks(chunks) == expected


# 4. Ordinary text should remain unchanged
def test_normal_text():
    text = "Hello! Your order has been shipped successfully."
    assert process_chunks([text]) == text


# 5. Invalid credit card checksum
def test_invalid_card_checksum():
    text = "Reference: 4111 1111 1111 1112."
    output = process_chunks([text])

    assert "[REDACTED]" not in output
    assert output == text


# 6. No sensitive information should leak
def test_no_sensitive_data_leaks():
    output = process_chunks(list(SAMPLE_TEXT))

    assert "john.smith@gmail.com" not in output
    assert "123-45-6789" not in output
    assert "4111 1111 1111 1111" not in output


# 7. Check buffer stays bounded across small chunks
def test_bounded_buffer():
    redactor = StreamingRedactor()

    for _ in range(1000):
        redactor.feed("Normal message text. ")

        assert len(redactor.buffer) <= redactor.max_buffer

    redactor.flush()


# 8. Safe text should not require the complete response
def test_incremental_output():
    redactor = StreamingRedactor()

    first = redactor.feed("Hello! ")
    second = redactor.feed("The customer details are available. ")

    assert first + second != ""

    final = redactor.flush()

    assert (
        first + second + final
        == "Hello! The customer details are available. "
    )


@pytest.mark.parametrize("text", [
    "4111 1111 1111 1111 123-45-6789.",
    "123-45-6789 987-65-4320.",
    "4111 1111 1111 1111 4111 1111 1111 1111.",
])
def test_adjacent_numeric_identifiers(text):
    assert process_chunks(list(text)) == "[REDACTED] [REDACTED]."


@pytest.mark.parametrize("text, expected", [
    ("123-john@example.com", "[REDACTED]"),
    ("SSN123-45-6789", "SSN[REDACTED]"),
])
def test_pii_in_word_candidates(text, expected):
    assert process_chunks(list(text)) == expected


@pytest.mark.parametrize("text, expected", [
    ("ID 123 456@example.com done", "ID 123 [REDACTED] done"),
    ("in 2024 12345@corp.com ok", "in 2024 [REDACTED] ok"),
    ("room 12 34bob@corp.com ok", "room 12 [REDACTED] ok"),
])
@pytest.mark.parametrize("chunk_size", [1, 3, 1000])
def test_email_after_spaced_number(text, expected, chunk_size):
    chunks = [
        text[i:i + chunk_size]
        for i in range(0, len(text), chunk_size)
    ]

    assert process_chunks(chunks) == expected


@pytest.mark.parametrize("text, expected", [
    ("Card-4111 1111 1111 1111 end", "Card-[REDACTED] end"),
    ("visa4111 1111 1111 1111 end", "visa[REDACTED] end"),
    ("x4111-1111 1111 1111 end", "x[REDACTED] end"),
])
@pytest.mark.parametrize("chunk_size", [1, 3, 1000])
def test_spaced_card_attached_to_word(text, expected, chunk_size):
    chunks = [
        text[i:i + chunk_size]
        for i in range(0, len(text), chunk_size)
    ]

    assert process_chunks(chunks) == expected


@pytest.mark.parametrize("text", [
    "version2 3 apples, 12 34.5% done",
    "Order A12 shipped on 2024 10 05 at noon.",
])
def test_digits_held_back_are_released_unchanged(text):
    assert process_chunks(list(text)) == text
