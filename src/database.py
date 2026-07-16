import logging
from datetime import datetime, timedelta
from decimal import Decimal
from math import isnan, isinf
from typing import Any
from fastapi import Request
from src import config


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

    if config.RETENTION_MONTHS and config.RETENTION_MONTHS > 0:
        ch_client.command(
            f"ALTER TABLE events MODIFY TTL event_time + INTERVAL {config.RETENTION_MONTHS} MONTH"
        )
    else:
        try:
            ch_client.command("ALTER TABLE events REMOVE TTL")
        except Exception as e:
            logging.debug(
                f"Attempted to remove table TTL but failed (it may not exist): {e}"
            )


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
