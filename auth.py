import config
from dataclasses import dataclass
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from database import get_ch_client

security_scheme = HTTPBearer(auto_error=False)

INGEST = "ingest"
READ = "read"
ADMIN = "admin"


@dataclass
class TokenContext:
    site_id: str
    scope: str


def _lookup_token(token: str) -> TokenContext | None:
    ch_client = get_ch_client()
    try:
        res = ch_client.query(
            "SELECT site_id, scope FROM api_tokens WHERE token = %(token)s LIMIT 1",
            {"token": token},
        )
        if not res.result_rows:
            return None
        site_id, scope = res.result_rows[0]
        return TokenContext(site_id=site_id, scope=str(scope))
    finally:
        ch_client.close()


def verify_api_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(security_scheme)
    ],
) -> TokenContext:
    if config.AUTH_DISABLED:
        return TokenContext(site_id=config.DEFAULT_SITE_ID, scope=ADMIN)

    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API authorization token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    ctx = _lookup_token(credentials.credentials)
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API authorization token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return ctx


def require_scope(*allowed_scopes: str):
    def _check(
        ctx: Annotated[TokenContext, Depends(verify_api_token)],
    ) -> TokenContext:
        if ctx.scope not in allowed_scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this action.",
            )
        return ctx

    return _check
