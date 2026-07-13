import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import config

security_scheme = HTTPBearer(auto_error=False)


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> str:
    if config.AUTH_DISABLED:
        return config.ANALYTICS_API_KEY

    token = credentials.credentials if credentials else None
    if not token or not secrets.compare_digest(token, config.ANALYTICS_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )
    return token
