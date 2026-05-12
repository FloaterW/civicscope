import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_tuple(name: str, default: str) -> tuple[str, ...]:
    raw = os.getenv(name, default)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _resolve_database_url() -> str:
    raw = os.getenv("DATABASE_URL")
    if raw is None:
        if os.getenv("APP_ENV", "development") != "development":
            raise RuntimeError("DATABASE_URL must be set in non-development environments")
        return _normalize_database_url("sqlite:///./civicscope.db")
    return _normalize_database_url(raw)


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "CivicScope")
    app_env: str = os.getenv("APP_ENV", "development")
    database_url: str = _resolve_database_url()
    seed_on_startup: bool = _env_bool("SEED_ON_STARTUP", True)
    force_reseed: bool = _env_bool("FORCE_RESEED", False)
    cors_origins: tuple[str, ...] = _env_tuple(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001,http://localhost:3002,http://127.0.0.1:3002,http://localhost:3101,http://127.0.0.1:3101",
    )


settings = Settings()
