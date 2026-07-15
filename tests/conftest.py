import pytest
import clickhouse_connect
from fastapi.testclient import TestClient
from src import config

TEST_DB = "test_analytics_db"


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    ch_client = clickhouse_connect.get_client(
        host=config.CH_HOST,
        port=config.CH_PORT,
        username=config.CH_USER,
        password=config.CH_PASSWORD,
    )
    ch_client.command(f"CREATE DATABASE IF NOT EXISTS {TEST_DB}")
    ch_client.close()

    original_db = config.CH_DB
    config.CH_DB = TEST_DB

    from src.database import init_db

    test_ch_client = clickhouse_connect.get_client(
        host=config.CH_HOST,
        port=config.CH_PORT,
        username=config.CH_USER,
        password=config.CH_PASSWORD,
        database=TEST_DB,
    )
    init_db(test_ch_client)
    test_ch_client.close()

    yield

    cleanup_client = clickhouse_connect.get_client(
        host=config.CH_HOST,
        port=config.CH_PORT,
        username=config.CH_USER,
        password=config.CH_PASSWORD,
    )
    cleanup_client.command(f"DROP DATABASE IF EXISTS {TEST_DB}")
    cleanup_client.close()
    config.CH_DB = original_db


@pytest.fixture
def clear_events_table():
    ch_client = clickhouse_connect.get_client(
        host=config.CH_HOST,
        port=config.CH_PORT,
        username=config.CH_USER,
        password=config.CH_PASSWORD,
        database=TEST_DB,
    )
    ch_client.command("TRUNCATE TABLE events")
    ch_client.close()
    yield


@pytest.fixture
def client():
    from src.main import app

    with TestClient(app) as c:
        yield c
