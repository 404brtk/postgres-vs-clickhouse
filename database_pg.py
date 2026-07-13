from datetime import datetime, timezone
from typing import Generator
from sqlalchemy import create_engine, ForeignKey
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column
import config

engine = create_engine(config.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )


class UserSession(Base):
    __tablename__ = "user_sessions"

    token: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )


class APIToken(Base):
    __tablename__ = "api_tokens"

    token: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    site_id: Mapped[str] = mapped_column(index=True, nullable=False)
    scope: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
