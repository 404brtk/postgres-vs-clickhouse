from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import clickhouse_connect
from config import (
    CH_DB,
    CH_HOST,
    CH_PASSWORD,
    CH_PORT,
    CH_USER,
    ANALYTICS_API_TOKEN,
    ANALYTICS_INGEST_TOKEN,
    DEFAULT_SITE_ID,
)
from routers import pages, analytics, tokens


@asynccontextmanager
async def lifespan(app: FastAPI):
    ch_client = clickhouse_connect.get_client(
        host=CH_HOST,
        port=CH_PORT,
        username=CH_USER,
        password=CH_PASSWORD,
        database=CH_DB,
    )
    try:
        ch_client.command("""
            CREATE TABLE IF NOT EXISTS events (
                event_id Int64,
                user_id Int32,
                site_id String,
                event_type LowCardinality(String),
                event_time DateTime,
                device LowCardinality(String),
                pathname LowCardinality(String),
                referrer LowCardinality(String),
                duration_sec Int32 DEFAULT 0,
                properties Map(String, String)
            ) ENGINE = MergeTree()
            ORDER BY (site_id, event_type, event_time, user_id);
        """)
        ch_client.command("""
            CREATE TABLE IF NOT EXISTS api_tokens (
                token String,
                site_id String,
                scope Enum8('ingest' = 1, 'read' = 2, 'admin' = 3),
                created_at DateTime DEFAULT now()
            ) ENGINE = MergeTree()
            ORDER BY (token);
        """)
        from datetime import datetime

        now = datetime.now()
        tokens = [
            (ANALYTICS_INGEST_TOKEN, DEFAULT_SITE_ID, "ingest", now),
            (ANALYTICS_API_TOKEN, DEFAULT_SITE_ID, "admin", now),
        ]
        for token, site_id, scope, ts in tokens:
            if token:
                exists = ch_client.query(
                    "SELECT 1 FROM api_tokens WHERE token = %(token)s LIMIT 1",
                    {"token": token},
                ).result_rows
                if not exists:
                    ch_client.insert(
                        "api_tokens",
                        data=[(token, site_id, scope, ts)],
                        column_names=["token", "site_id", "scope", "created_at"],
                    )
    except Exception:
        pass
    finally:
        ch_client.close()
    yield


app = FastAPI(title="API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(pages.router)
app.include_router(analytics.router)
app.include_router(tokens.router)
