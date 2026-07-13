import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from pwdlib import PasswordHash
from database_pg import get_db, User, UserSession
from models import UserRegister, UserLogin

router = APIRouter()
security_scheme = HTTPBearer(auto_error=False)
password_hash = PasswordHash.recommended()



@router.get("/api/auth/status")
def auth_status(db: Session = Depends(get_db)):
    user_count = db.query(User).count()
    return {"registration_required": user_count == 0}


@router.post("/api/auth/register")
def register(spec: UserRegister, db: Session = Depends(get_db)):
    if not spec.username or not spec.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password are required.",
        )

    existing_user = db.query(User).filter(User.username == spec.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username is already taken.",
        )

    db_user = User(
        username=spec.username,
        password_hash=password_hash.hash(spec.password),
    )
    db.add(db_user)
    db.commit()
    return {"status": "success", "message": "User registered successfully."}


@router.post("/api/auth/login")
def login(spec: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == spec.username).first()

    try:
        is_verified = (
            password_hash.verify(spec.password, user.password_hash) if user else False
        )
    except Exception:
        is_verified = False

    if not user or not is_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=24)

    db_session = UserSession(
        token=token,
        user_id=user.id,
        expires_at=expires_at,
    )
    db.add(db_session)
    db.commit()

    return {"token": token, "expires_at": str(expires_at)}


@router.post("/api/auth/logout")
def logout(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(security_scheme)
    ],
    db: Session = Depends(get_db),
):
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing credentials.",
        )
    token = credentials.credentials
    db_session = db.query(UserSession).filter(UserSession.token == token).first()
    if db_session:
        db.delete(db_session)
        db.commit()
    return {"status": "success", "message": "Logged out successfully."}
