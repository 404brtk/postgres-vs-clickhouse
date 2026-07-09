from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Union
import psycopg
import clickhouse_connect
from config import PG_DSN, CH_HOST, CH_PORT, CH_USER, CH_PASSWORD, CH_DB

def get_pg_connection():
    return psycopg.connect(PG_DSN)

def get_ch_client():
    return clickhouse_connect.get_client(
        host=CH_HOST,
        port=CH_PORT,
        username=CH_USER,
        password=CH_PASSWORD,
        database=CH_DB
    )

def execute_generic_sql(db: str, sql: str, params: Union[dict, list]) -> list[dict[str, Any]]:
    rows = []
    column_names = []
    
    if db == "postgres":
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                if cur.description:
                    column_names = [col.name for col in cur.description]
                    rows = cur.fetchall()
    elif db == "clickhouse":
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
        return val
        
    return [{k: json_serializable(v) for k, v in row.items()} for row in results]
