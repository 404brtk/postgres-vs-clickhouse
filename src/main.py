import clickhouse_connect
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from src.config import (
    CH_DB,
    CH_HOST,
    CH_PASSWORD,
    CH_PORT,
    CH_USER,
)
from src.routers import pages, analytics
from src.database import init_db


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
        init_db(ch_client)
    except Exception as e:
        logging.error(f"ClickHouse initialization failed: {e}")
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
