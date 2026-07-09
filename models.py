from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel

class EventPayload(BaseModel):
    target_id: int | None = 0
    category_id: int | None = 0
    event_type: str
    duration_sec: int | None = 0
    is_liked: int | None = 0
    device: str | None = "desktop"
    pathname: str = ""
    referrer: str = ""
    commission: float | None = 0.0

class GenericEvent(BaseModel):
    event_type: str
    device: str | None = "desktop"
    pathname: str = ""
    referrer: str = ""
    duration_sec: int | None = 0

    model_config = {
        "extra": "allow"
    }

class MetricSpec(BaseModel):
    type: Literal["count", "uniq", "sum", "avg", "min", "max"]
    field: str | None = None
    alias: str | None = None

class FilterSpec(BaseModel):
    field: str
    operator: Literal["eq", "neq", "gt", "gte", "lt", "lte", "in", "like"]
    value: Any

class QuerySpec(BaseModel):
    target_db: Literal["clickhouse", "postgres"] = "clickhouse"
    target_table: Literal["generic_events", "user_events"] = "generic_events"
    start_date: datetime | None = None
    end_date: datetime | None = None
    metrics: list[MetricSpec]
    group_by: list[str] | None = None
    filters: list[FilterSpec] | None = None
    limit: int | None = 100

class CompareQuerySpec(BaseModel):
    target_table: Literal["generic_events", "user_events"] = "generic_events"
    start_date: datetime | None = None
    end_date: datetime | None = None
    metrics: list[MetricSpec]
    group_by: list[str] | None = None
    filters: list[FilterSpec] | None = None
    limit: int | None = 100
