import os
import hashlib
import secrets
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

CH_HOST = "localhost"
CH_PORT = 8123
CH_USER = "default"
CH_PASSWORD = "clickhouse_password"
CH_DB = "default"
AUTH_DISABLED = os.environ.get("AUTH_DISABLED", "").lower() in ("1", "true", "yes")
DEFAULT_SITE_ID = os.environ.get("DEFAULT_SITE_ID", "default")

PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = int(os.environ.get("PG_PORT", "5432"))
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "postgres_password")
PG_DB = os.environ.get("PG_DB", "metadata_db")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"postgresql+psycopg://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
)

SECRET_KEY_FILE = ".secret_key"
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
    return int(sha_hex[:8], 16) % 100000 + 1
