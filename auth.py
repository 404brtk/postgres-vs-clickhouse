from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
import config
from database_pg import get_db, APIToken, UserSession
from models import TokenScope

security_scheme = HTTPBearer(auto_error=False)


@dataclass
class TokenContext:
    site_id: str
    scope: str
    user_id: int | None = None


def verify_api_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(security_scheme)
    ],
    db: Session = Depends(get_db),
) -> TokenContext:
    if config.AUTH_DISABLED:
        return TokenContext(site_id=config.DEFAULT_SITE_ID, scope=TokenScope.ADMIN)

    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API authorization token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_str = credentials.credentials

    session = db.query(UserSession).filter(UserSession.token == token_str).first()
    if session:
        if session.expires_at > datetime.now(timezone.utc).replace(tzinfo=None):
            return TokenContext(
                site_id=config.DEFAULT_SITE_ID, scope=TokenScope.ADMIN, user_id=session.user_id
            )
        else:
            db.delete(session)
            db.commit()

    api_token = db.query(APIToken).filter(APIToken.token == token_str).first()
    if api_token:
        return TokenContext(
            site_id=api_token.site_id, scope=api_token.scope, user_id=api_token.user_id
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API authorization token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


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
