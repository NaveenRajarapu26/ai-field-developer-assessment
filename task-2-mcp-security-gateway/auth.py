
import secrets

from fastapi import HTTPException


# Demo credentials only.
# In production, validate JWTs or use an identity provider.
DEMO_TOKENS = {
    "demo-admin-token": "admin",
    "demo-viewer-token": "viewer",
}


def get_user_role(authorization: str | None) -> str:
    """Validate the Bearer token and return the user's role."""

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header"
        )

    scheme, separator, token = authorization.partition(" ")

    if (
        not separator
        or scheme.lower() != "bearer"
        or not token
        or token != token.strip()
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header"
        )

    for known_token, role in DEMO_TOKENS.items():
        if secrets.compare_digest(token.encode("utf-8"), known_token.encode("utf-8")):
            return role

    raise HTTPException(
        status_code=401,
        detail="Invalid authentication token"
    )
