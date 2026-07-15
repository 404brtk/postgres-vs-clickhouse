from datetime import datetime, timedelta
from decimal import Decimal
from math import isnan, isinf
from typing import Any
import clickhouse_connect
from src.config import CH_HOST, CH_PORT, CH_USER, CH_PASSWORD, CH_DB


def get_ch_client():
    return clickhouse_connect.get_client(
        host=CH_HOST,
        port=CH_PORT,
        username=CH_USER,
        password=CH_PASSWORD,
        database=CH_DB,
    )


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


def execute_sql(sql: str, params: dict) -> list[dict[str, Any]]:
    ch_client = get_ch_client()
    res = ch_client.query(sql, params)
    column_names = res.column_names
    rows = res.result_rows
    ch_client.close()

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
