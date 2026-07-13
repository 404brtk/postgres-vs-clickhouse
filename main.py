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
)
from routers import pages, analytics, tokens, auth


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
app.include_router(auth.router)
