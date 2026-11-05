
import asyncio
import logging
import os

import httpx


logger = logging.getLogger("model-router")

PRIMARY_URL = os.getenv(
    "PRIMARY_MODEL_URL",
    "http://127.0.0.1:8001/primary"
)

BACKUP_URL = os.getenv(
    "BACKUP_MODEL_URL",
    "http://127.0.0.1:8001/backup"
)

PRIMARY_TIMEOUT = 3.0
BACKUP_TIMEOUT = 5.0


class GatewayError(Exception):
    """A controlled error that is safe to return to clients."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 502
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


async def request_model(
    client: httpx.AsyncClient,
    url: str,
    payload: dict,
    timeout_seconds: float
) -> httpx.Response:
    """Send a request with a total deadline."""

    async with asyncio.timeout(timeout_seconds):
        return await client.post(
            url,
            json=payload
        )


async def route_completion(payload: dict) -> dict:
    """
    Use primary model first.

    Fail over only when primary returns HTTP 429
    or exceeds the three-second deadline.
    """

    async with httpx.AsyncClient() as client:

        use_backup = False

        # 1. Try primary provider
        try:
            response = await request_model(
                client,
                PRIMARY_URL,
                payload,
                PRIMARY_TIMEOUT
            )

            if response.status_code == 429:
                logger.warning(
                    "Primary model rate-limited; using backup"
                )
                use_backup = True

            elif response.status_code == 200:
                try:
                    result = response.json()
                    if not isinstance(result, dict):
                        raise ValueError("Invalid provider payload")
                    return {
                        "provider": "primary",
                        "result": result
                    }
                except ValueError:
                    raise GatewayError(
                        "INVALID_UPSTREAM_RESPONSE",
                        "Model provider returned an invalid response"
                    )

            else:
                logger.warning(
                    "Primary provider returned HTTP %s",
                    response.status_code
                )
                raise GatewayError(
                    "UPSTREAM_ERROR",
                    "Primary model provider failed"
                )

        except (TimeoutError, httpx.TimeoutException):
            logger.warning(
                "Primary model timed out; using backup"
            )
            use_backup = True

        except httpx.RequestError:
            logger.error("Primary provider connection failed")
            raise GatewayError(
                "UPSTREAM_UNAVAILABLE",
                "Primary model provider unavailable"
            )

        # 2. Fallback to backup provider
        if use_backup:
            try:
                response = await request_model(
                    client,
                    BACKUP_URL,
                    payload,
                    BACKUP_TIMEOUT
                )

                if response.status_code != 200:
                    logger.warning(
                        "Backup provider returned HTTP %s",
                        response.status_code
                    )
                    raise GatewayError(
                        "BACKUP_FAILED",
                        "Backup model provider failed"
                    )

                try:
                    result = response.json()
                    if not isinstance(result, dict):
                        raise ValueError("Invalid provider payload")
                except ValueError:
                    raise GatewayError(
                        "INVALID_UPSTREAM_RESPONSE",
                        "Backup model returned an invalid response"
                    )

                return {
                    "provider": "backup",
                    "result": result
                }

            except (TimeoutError, httpx.TimeoutException):
                raise GatewayError(
                    "BACKUP_TIMEOUT",
                    "Backup model provider timed out",
                    status_code=504
                )

            except httpx.RequestError:
                raise GatewayError(
                    "BACKUP_UNAVAILABLE",
                    "Backup model provider unavailable"
                )

    raise GatewayError(
        "ROUTING_ERROR",
        "Unable to route model request"
    )
