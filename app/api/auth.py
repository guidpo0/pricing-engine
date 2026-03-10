"""
Dependencies for API Authentication.
"""
import logging
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import APIKeyHeader
from app.config import settings

logger = logging.getLogger(__name__)

# Try to get token from X-API-Key header. It's optional so we can check both forms or fallback if missing.
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_token(request: Request, api_key: str | None = Depends(api_key_header)) -> bool:
    """
    Dependency to verify the request provides a valid API token if one is configured.
    Checks `Authorization: Bearer <token>` or `X-API-Key: <token>`.
    """
    configured_token = settings.api_auth_token
    if not configured_token:
        # If no token is configured in .env, accept all requests (disabled auth)
        return True

    # 1. Check X-API-Key
    if api_key and api_key == configured_token:
        return True
    
    # 2. Check Authorization Bearer
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        bearer_token = auth_header.split(" ")[1]
        if bearer_token == configured_token:
            return True

    logger.warning("Unauthorized access attempt to %s", request.url.path)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
