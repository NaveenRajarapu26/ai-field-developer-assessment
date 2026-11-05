
import sqlite3
import time
from dataclasses import dataclass

from database import get_connection, initialize_database


# Default rate limiting configuration
TOKEN_LIMIT = 50_000
WINDOW_SECONDS = 60


@dataclass
class RateLimitResult:
    allowed: bool
    used_tokens: int
    remaining_tokens: int
    retry_after: float = 0.0


class TokenRateLimiter:

    def __init__(
        self,
        limit: int = TOKEN_LIMIT,
        window: int = WINDOW_SECONDS
    ):
        if limit <= 0 or window <= 0:
            raise ValueError("Limit and window must be positive")

        self.limit = limit
        self.window = window

        initialize_database()

    def reserve(
        self,
        tenant_key: str,
        tokens: int,
        now: float | None = None
    ) -> RateLimitResult:
        """
        Atomically check and reserve tokens for a tenant.
        """

        if not isinstance(tenant_key, str) or not tenant_key:
            raise ValueError("Tenant identifier is required")

        if type(tokens) is not int or tokens <= 0:
            raise ValueError("Tokens must be a positive integer")

        connection = get_connection()

        try:
            # Acquire write lock before checking usage
            connection.execute("BEGIN IMMEDIATE")

            # Timestamp admission after waiting for the SQLite write lock.
            current_time = time.time() if now is None else now
            cutoff = current_time - self.window

            # Remove expired records
            connection.execute(
                "DELETE FROM token_usage WHERE timestamp <= ?",
                (cutoff,)
            )

            # Calculate tokens reserved in current window
            row = connection.execute(
                """
                SELECT COALESCE(SUM(tokens), 0) AS total
                FROM token_usage
                WHERE tenant_key = ?
                AND timestamp > ?
                """,
                (tenant_key, cutoff)
            ).fetchone()

            used = int(row["total"])

            # Reject if request exceeds available budget
            if used + tokens > self.limit:

                # Find when enough existing reservations expire
                reservations = connection.execute(
                    """
                    SELECT timestamp, tokens
                    FROM token_usage
                    WHERE tenant_key = ?
                    AND timestamp > ?
                    ORDER BY timestamp ASC, id ASC
                    """,
                    (tenant_key, cutoff)
                ).fetchall()

                required = used + tokens - self.limit
                expired_tokens = 0
                retry_after = 0.0

                for reservation in reservations:
                    expired_tokens += reservation["tokens"]

                    retry_after = max(
                        0.0,
                        reservation["timestamp"]
                        + self.window
                        - current_time
                    )

                    if expired_tokens >= required:
                        break

                connection.commit()

                return RateLimitResult(
                    allowed=False,
                    used_tokens=used,
                    remaining_tokens=max(0, self.limit - used),
                    retry_after=retry_after
                )

            # Reserve tokens
            connection.execute(
                """
                INSERT INTO token_usage
                (tenant_key, tokens, timestamp)
                VALUES (?, ?, ?)
                """,
                (tenant_key, tokens, current_time)
            )

            connection.commit()

            return RateLimitResult(
                allowed=True,
                used_tokens=used + tokens,
                remaining_tokens=self.limit - used - tokens
            )

        except sqlite3.Error:
            connection.rollback()
            raise

        finally:
            connection.close()


if __name__ == "__main__":

    limiter = TokenRateLimiter()

    result = limiter.reserve(
        tenant_key="demo-tenant-A",
        tokens=10_000
    )

    print("Allowed:", result.allowed)
    print("Used tokens:", result.used_tokens)
    print("Remaining tokens:", result.remaining_tokens)
