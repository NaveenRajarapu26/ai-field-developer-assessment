
from rate_limiter import TokenRateLimiter


limiter = TokenRateLimiter()

from uuid import uuid4

tenant = f"demo-{uuid4().hex}"

start = 1_900_000_000.0


def show(label, result):
    print(f"\n{label}")
    print("Allowed:", result.allowed)
    print("Used tokens:", result.used_tokens)
    print("Remaining:", result.remaining_tokens)
    print("Retry after:", result.retry_after)


# Two accepted requests
first = limiter.reserve(tenant, 20_000, now=start)
second = limiter.reserve(tenant, 25_000, now=start + 10)

# Exceeds remaining budget
third = limiter.reserve(tenant, 10_000, now=start + 20)

# Original reservation has expired
fourth = limiter.reserve(tenant, 10_000, now=start + 61)

show("Request 1", first)
show("Request 2", second)
show("Request 3", third)
show("Request 4", fourth)

assert first.allowed is True
assert second.allowed is True
assert third.allowed is False
assert fourth.allowed is True

print("\nPASS: Sliding window rate limiting works")
