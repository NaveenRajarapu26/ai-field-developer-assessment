
import re


REDACTED = "[REDACTED]"

# Patterns for sensitive information
EMAIL = re.compile(
    r"(?<![A-Za-z0-9._%+-])"
    r"[A-Za-z0-9][A-Za-z0-9._%+-]{0,63}@"
    r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
)

CARD = re.compile(r"[0-9](?:[ -]?[0-9]){12,18}\Z")
SSN_IN_TEXT = re.compile(r"(?<![0-9])[0-9]{3}-[0-9]{2}-[0-9]{4}(?![0-9])")
NUMBER_TAIL = re.compile(r"[0-9][0-9-]*\Z")


def redact_numbers(candidate: str) -> str:
    """Redact individual identifiers even when a candidate contains several."""
    candidate = SSN_IN_TEXT.sub(REDACTED, candidate)
    output = []
    position = 0
    while position < len(candidate):
        end_match = None
        if candidate[position] in "0123456789" and (
            position == 0 or candidate[position - 1] not in "0123456789"
        ):
            # At most 19 digits and 18 separators; search is bounded.
            for end in range(min(len(candidate), position + 37), position + 12, -1):
                if end < len(candidate) and candidate[end] in "0123456789":
                    continue
                value = candidate[position:end]
                if CARD.fullmatch(value) and valid_card(value):
                    end_match = end
                    break
        if end_match is not None:
            output.append(REDACTED)
            position = end_match
        else:
            output.append(candidate[position])
            position += 1
    return "".join(output)

WORD_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789._%+-@"
)

WORD_START = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_+%"
)

NUMBER_CHARS = frozenset("0123456789 -")


# 1. Validate credit card using Luhn algorithm
def valid_card(value: str) -> bool:

    digits = [
        int(char)
        for char in value
        if char.isdigit()
    ]

    if not 13 <= len(digits) <= 19:
        return False

    total = 0

    for i, digit in enumerate(reversed(digits)):

        if i % 2:
            digit *= 2

            if digit > 9:
                digit -= 9

        total += digit

    return total % 10 == 0


# 2. Stateful streaming PII redactor
class StreamingRedactor:

    def __init__(self, max_buffer: int = 384):

        if max_buffer < 64:
            raise ValueError(
                "max_buffer must be at least 64"
            )

        self.max_buffer = max_buffer
        self.buffer = ""
        self.kind = None
        self.discarding = False

    # Process a completed candidate
    def _finalize(self) -> str:

        candidate = self.buffer
        kind = self.kind

        self.buffer = ""
        self.kind = None

        # Email detection
        if kind == "word":
            return redact_numbers(EMAIL.sub(REDACTED, candidate))

        # SSN and credit card detection
        if kind == "number":
            return redact_numbers(candidate)

        return candidate

    # Finalize a candidate but hold back its unredacted trailing digits,
    # which may start an identifier that continues in the next candidate.
    def _finalize_keeping_tail(self) -> tuple[str, str]:

        safe = self._finalize()
        tail = NUMBER_TAIL.search(safe)

        if tail is None:
            return safe, ""

        return safe[:tail.start()], tail.group()

    # Process incoming streaming text
    def feed(
        self,
        chunk: str,
        final: bool = False
    ) -> str:

        if not isinstance(chunk, str):
            raise TypeError("chunk must be a string")

        output = []

        for char in chunk:

            # Discard oversized ambiguous candidates
            if self.discarding:

                if char in WORD_CHARS or char in " ":
                    continue

                self.discarding = False
                output.append(char)
                continue

            # Handle numeric candidates
            if self.kind == "number":

                if char in NUMBER_CHARS:
                    self.buffer += char

                elif (
                    char in WORD_CHARS
                    and " " not in self.buffer
                ):
                    # Example: 123john@example.com
                    self.kind = "word"
                    self.buffer += char

                else:
                    # Example: 123 456@example.com
                    safe, tail = (
                        self._finalize_keeping_tail()
                        if char in WORD_CHARS
                        else (self._finalize(), "")
                    )

                    output.append(safe)

                    if tail:

                        self.kind = "word"
                        self.buffer = tail + char

                    elif char in WORD_START:

                        self.kind = (
                            "number"
                            if char.isascii() and char.isdigit()
                            else "word"
                        )

                        self.buffer = char

                    else:
                        output.append(char)

            # Handle possible email candidates
            elif self.kind == "word":

                if char in WORD_CHARS:
                    self.buffer += char

                elif char == " ":
                    # Example: Card-4111 1111 1111 1111
                    safe, tail = self._finalize_keeping_tail()

                    output.append(safe)

                    if tail:

                        self.kind = "number"
                        self.buffer = tail + char

                    else:
                        output.append(char)

                else:
                    output.append(self._finalize())

                    if char in WORD_START:

                        self.kind = (
                            "number"
                            if char.isascii() and char.isdigit()
                            else "word"
                        )

                        self.buffer = char

                    else:
                        output.append(char)

            # Start a new candidate
            elif char in WORD_START:

                self.kind = (
                    "number"
                    if char.isascii() and char.isdigit()
                    else "word"
                )

                self.buffer = char

            # Ordinary character
            else:
                output.append(char)

            # Enforce bounded candidate memory
            if len(self.buffer) > self.max_buffer:

                output.append(REDACTED)

                self.buffer = ""
                self.kind = None
                self.discarding = True

        # Flush remaining candidate at stream end
        if final and not self.discarding and self.buffer:
            output.append(self._finalize())

        elif final:
            self.discarding = False

        return "".join(output)

    def flush(self) -> str:
        return self.feed("", final=True)
