
from redactor import StreamingRedactor


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


redactor = StreamingRedactor()

print("=== STREAMING REDACTION TEST ===")

output = ""

for chunk in chunks:
    safe_text = redactor.feed(chunk)
    output += safe_text

    if safe_text:
        print("Safe output:", safe_text)

output += redactor.flush()

print("\n=== FINAL RESULT ===")
print(output)

assert "john.smith@gmail.com" not in output
assert "123-45-6789" not in output
assert "4111 1111 1111 1111" not in output
assert output.count("[REDACTED]") == 3

print("\nPASS: All three sensitive values redacted")
