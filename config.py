import os
import hashlib
import secrets
from datetime import datetime

CH_HOST = "localhost"
CH_PORT = 8123
CH_USER = "default"
CH_PASSWORD = "clickhouse_password"
CH_DB = "default"

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
    SECRET_KEY = os.environ.get("APP_SECRET_KEY", "fallback-static-benchmark-secret-key")

def get_daily_salt() -> str:
    today_str = datetime.now().strftime("%Y-%m-%d")
    return hashlib.sha256(f"{SECRET_KEY}-{today_str}".encode("utf-8")).hexdigest()

def generate_user_hash(client_ip: str, user_agent: str) -> int:
    salt = get_daily_salt()
    session_str = f"{client_ip}-{user_agent}-{salt}"
    sha_hex = hashlib.sha256(session_str.encode("utf-8")).hexdigest()
    return int(sha_hex[:8], 16) % 100000 + 1
