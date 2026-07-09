from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import psycopg
import clickhouse_connect
from config import PG_DSN, CH_HOST, CH_PORT, CH_USER, CH_PASSWORD, CH_DB
from routers import pages, benchmark, analytics

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        with psycopg.connect(PG_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS generic_events (
                        event_id BIGINT PRIMARY KEY,
                        user_id INT,
                        event_type VARCHAR(100),
                        event_time TIMESTAMP,
                        device VARCHAR(50),
                        pathname VARCHAR(500),
                        referrer VARCHAR(500),
                        duration_sec INT DEFAULT 0,
                        properties JSONB
                    );
                    ALTER TABLE generic_events ADD COLUMN IF NOT EXISTS duration_sec INT DEFAULT 0;
                    CREATE INDEX IF NOT EXISTS idx_generic_events_type_time ON generic_events (event_type, event_time);
                """)
                conn.commit()
    except Exception:
        pass

    try:
        ch_client = clickhouse_connect.get_client(
            host=CH_HOST,
            port=CH_PORT,
            username=CH_USER,
            password=CH_PASSWORD,
            database=CH_DB
        )
        ch_client.command("""
            CREATE TABLE IF NOT EXISTS generic_events (
                event_id Int64,
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
        try:
            ch_client.command("ALTER TABLE generic_events ADD COLUMN IF NOT EXISTS duration_sec Int32 DEFAULT 0;")
        except Exception:
            pass
        ch_client.close()
    except Exception:
        pass
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
app.include_router(benchmark.router)
app.include_router(analytics.router)
