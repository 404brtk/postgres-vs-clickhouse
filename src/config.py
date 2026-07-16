import os
import hashlib
import secrets
from datetime import datetime
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_user: str = "default"
    clickhouse_password: str = "clickhouse_password"  # noqa: S105
    clickhouse_db: str = "default"

    analytics_api_key: str = "demo-api-key"
    auth_disabled: bool = False


settings = Settings()

CH_HOST = settings.clickhouse_host
CH_PORT = settings.clickhouse_port
CH_USER = settings.clickhouse_user
CH_PASSWORD = settings.clickhouse_password
CH_DB = settings.clickhouse_db

ANALYTICS_API_KEY = settings.analytics_api_key
AUTH_DISABLED = settings.auth_disabled

SECRET_KEY_FILE = str(Path(__file__).parent.parent / ".secret_key")  # noqa: S105
try:
    if os.path.exists(SECRET_KEY_FILE):
        with open(SECRET_KEY_FILE, "r") as f:
            SECRET_KEY = f.read().strip()
    else:
        SECRET_KEY = secrets.token_hex(32)
        with open(SECRET_KEY_FILE, "w") as f:
            f.write(SECRET_KEY)
except Exception:
    SECRET_KEY = os.environ.get(
        "APP_SECRET_KEY", "fallback-static-benchmark-secret-key"
    )


def get_daily_salt() -> str:
    today_str = datetime.now().strftime("%Y-%m-%d")
    return hashlib.sha256(f"{SECRET_KEY}-{today_str}".encode("utf-8")).hexdigest()


def generate_user_hash(client_ip: str, user_agent: str) -> int:
    salt = get_daily_salt()
    session_str = f"{client_ip}-{user_agent}-{salt}"
    sha_hex = hashlib.sha256(session_str.encode("utf-8")).hexdigest()
    return (int(sha_hex[:8], 16) & 0x7FFFFFFF) or 1
