import secrets
from datetime import datetime
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from database import execute_sql, get_ch_client
from models import TokenCreate
from auth import TokenContext, require_scope

router = APIRouter()


@router.get("/api/tokens")
def list_tokens(
    ctx: Annotated[TokenContext, Depends(require_scope("admin"))],
):
    return execute_sql(
        "SELECT token, site_id, scope, created_at FROM api_tokens ORDER BY created_at",
        {},
    )


@router.post("/api/tokens")
def create_token(
    spec: TokenCreate,
    ctx: Annotated[TokenContext, Depends(require_scope("admin"))],
):
    token = secrets.token_urlsafe(32)
    try:
        ch_client = get_ch_client()
        ch_client.insert(
            "api_tokens",
            data=[(token, spec.site_id, spec.scope, datetime.now())],
            column_names=["token", "site_id", "scope", "created_at"],
        )
        ch_client.close()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create token: {str(e)}",
        )
    return {"token": token, "site_id": spec.site_id, "scope": spec.scope}


@router.delete("/api/tokens/{token}")
def revoke_token(
    token: str,
    ctx: Annotated[TokenContext, Depends(require_scope("admin"))],
):
    try:
        ch_client = get_ch_client()
        ch_client.command(
            "ALTER TABLE api_tokens DELETE WHERE token = %(token)s",
            {"token": token},
        )
        ch_client.close()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke token: {str(e)}",
        )
    return {"status": "success", "message": "Token revoked."}
