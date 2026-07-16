"""Application configuration loaded from environment variables."""
import os
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")


class Settings:
    MONGO_URL: str = os.environ["MONGO_URL"]
    DB_NAME: str = os.environ["DB_NAME"]
    CORS_ORIGINS: list[str] = os.environ.get("CORS_ORIGINS", "*").split(",")

    JWT_SECRET: str = os.environ.get("JWT_SECRET", "insecure-dev-secret-change-me")
    JWT_ALGORITHM: str = os.environ.get("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "14"))

    ENROLLMENT_CODE_TTL_MINUTES: int = int(os.environ.get("ENROLLMENT_CODE_TTL_MINUTES", "10"))
    DEVICE_OFFLINE_THRESHOLD_SECONDS: int = int(os.environ.get("DEVICE_OFFLINE_THRESHOLD_SECONDS", "90"))

    # --- Device (agent) JWT lifetimes ---
    # Access token: short (agent refreshes automatically well before expiry).
    # Refresh token: long-lived so a device that boots after weeks offline can
    # still get back online without re-pairing.
    DEVICE_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("DEVICE_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    DEVICE_REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.environ.get("DEVICE_REFRESH_TOKEN_EXPIRE_DAYS", "365"))

    # --- Default agent intervals (server-controlled, pushed on pair) ---
    AGENT_HEARTBEAT_INTERVAL_SEC: int = int(os.environ.get("AGENT_HEARTBEAT_INTERVAL_SEC", "30"))
    AGENT_TELEMETRY_INTERVAL_SEC: int = int(os.environ.get("AGENT_TELEMETRY_INTERVAL_SEC", "10"))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
