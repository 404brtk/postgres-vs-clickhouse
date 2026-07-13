from datetime import datetime
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel


class TokenScope(str, Enum):
    INGEST = "ingest"
    READ = "read"
    ADMIN = "admin"


class GenericEvent(BaseModel):
    event_type: str
    device: str | None = "desktop"
    pathname: str = ""
    referrer: str = ""
    duration_sec: int | None = 0

    model_config = {"extra": "allow"}


class TokenCreate(BaseModel):
    site_id: str
    scope: TokenScope


class MetricSpec(BaseModel):
    type: Literal["count", "uniq", "sum", "avg", "min", "max"]
    field: str | None = None
    alias: str | None = None


class FilterSpec(BaseModel):
    field: str
    operator: Literal["eq", "neq", "gt", "gte", "lt", "lte", "in", "like"]
    value: Any


class QuerySpec(BaseModel):
    start_date: datetime | None = None
    end_date: datetime | None = None
    metrics: list[MetricSpec]
    group_by: list[str] | None = None
    filters: list[FilterSpec] | None = None
    limit: int | None = 100


class UserRegister(BaseModel):
    username: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str

