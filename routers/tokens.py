import secrets
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database_pg import get_db, APIToken
from models import TokenCreate
from auth import TokenContext, require_scope

router = APIRouter()


@router.get("/api/tokens")
def list_tokens(
    ctx: Annotated[TokenContext, Depends(require_scope("admin"))],
    db: Session = Depends(get_db),
):
    tokens = (
        db.query(APIToken)
        .filter(APIToken.user_id == ctx.user_id)
        .order_by(APIToken.created_at)
        .all()
    )
    return [
        {
            "token": t.token,
            "site_id": t.site_id,
            "scope": t.scope,
            "created_at": str(t.created_at),
        }
        for t in tokens
    ]


@router.post("/api/tokens")
def create_token(
    spec: TokenCreate,
    ctx: Annotated[TokenContext, Depends(require_scope("admin"))],
    db: Session = Depends(get_db),
):
    token = secrets.token_urlsafe(32)
    try:
        db_token = APIToken(
            token=token, user_id=ctx.user_id, site_id=spec.site_id, scope=spec.scope
        )
        db.add(db_token)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create token: {str(e)}",
        )
    return {"token": token, "site_id": spec.site_id, "scope": spec.scope}


@router.delete("/api/tokens/{token}")
def revoke_token(
    token: str,
    ctx: Annotated[TokenContext, Depends(require_scope("admin"))],
    db: Session = Depends(get_db),
):
    db_token = (
        db.query(APIToken)
        .filter(APIToken.token == token, APIToken.user_id == ctx.user_id)
        .first()
    )
    if not db_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found.",
        )
    try:
        db.delete(db_token)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke token: {str(e)}",
        )
    return {"status": "success", "message": "Token revoked."}


@router.get("/api/sites")
def list_sites(
    ctx: Annotated[TokenContext, Depends(require_scope("admin"))],
    db: Session = Depends(get_db),
):
    tokens = (
        db.query(APIToken.site_id)
        .filter(APIToken.user_id == ctx.user_id)
        .distinct()
        .all()
    )
    return [t[0] for t in tokens]
