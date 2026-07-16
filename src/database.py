from datetime import datetime, timedelta
from decimal import Decimal
from math import isnan, isinf
from typing import Any
from fastapi import Request


def get_ch_client(request: Request):
    return request.app.state.ch_client


def init_db(ch_client):
    ch_client.command("""
        CREATE TABLE IF NOT EXISTS events (
            event_id UUID DEFAULT generateUUIDv4(),
            user_id Int32,
            event_type LowCardinality(String),
            event_time DateTime,
            device LowCardinality(String),
            pathname LowCardinality(String),
            referrer LowCardinality(String),
            duration_sec Int32 DEFAULT 0,
            properties Map(String, String)
        ) ENGINE = MergeTree()
        ORDER BY (event_type, event_time, user_id);
    """)


def execute_sql(ch_client, sql: str, params: dict) -> list[dict[str, Any]]:
    res = ch_client.query(sql, params)
    column_names = res.column_names
    rows = res.result_rows

    results = [dict(zip(column_names, row)) for row in rows]

    def json_serializable(val):
        if isinstance(val, (datetime, timedelta)):
            return str(val)
        if isinstance(val, Decimal):
            return float(val)
        if isinstance(val, float) and (isnan(val) or isinf(val)):
            return 0
        return val

    return [{k: json_serializable(v) for k, v in row.items()} for row in results]
