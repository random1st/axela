"""Basic authentication middleware."""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from axela.config import get_settings

security = HTTPBasic()


def verify_credentials(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
) -> str:
    """Verify basic auth credentials.

    Args:
        credentials: HTTP Basic credentials.

    Returns:
        Username if valid.

    Raises:
        HTTPException: If credentials are invalid.

    """
    settings = get_settings()

    # Skip auth if not configured
    if not settings.basic_auth_enabled:
        return "anonymous"

    correct_username = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        settings.basic_auth_username.encode("utf-8"),
    )
    correct_password = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        settings.basic_auth_password.get_secret_value().encode("utf-8"),
    )

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials.username
