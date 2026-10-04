"""Central application configuration.

Every runtime knob lives here so that the CLI, the Airflow DAG, the tests and the
FastAPI app all read the exact same values.  Values are loaded from (in order of
precedence) real environment variables, a local ``.env`` file and the defaults
declared on :class:`Settings`.
"""

from __future__ import annotations

import functools
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# --------------------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[2]
APP_DIR = ROOT_DIR / "app"
DB_DIR = ROOT_DIR / "db"
DOCS_DIR = ROOT_DIR / "docs"
FRONTEND_DIR = ROOT_DIR / "frontend"
VAR_DIR = ROOT_DIR / "var"
DEFAULT_SQLITE_PATH = VAR_DIR / "pipeline.sqlite3"


class Settings(BaseSettings):
    """Typed, validated application settings."""

    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------------------------------------------------------------- identity
    app_name: str = "Product Intelligence Pipeline"
    app_env: Literal["development", "testing", "production"] = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_timezone: str = "UTC"
    app_log_level: str = "INFO"
    app_log_format: Literal["text", "json"] = "text"
    app_version: str = "1.0.0"

    # ---------------------------------------------------------------- database
    database_url: str = f"sqlite:///{DEFAULT_SQLITE_PATH}"
    mysql_url: str = ""
    active_database: Literal["postgres", "mysql", "sqlite"] = "postgres"
    db_schema: str = "public"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 1800
    db_statement_timeout_ms: int = 30_000

    # ---------------------------------------------------------------- security
    secret_key: str = "dev-only-insecure-key-change-me-please-32ch"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 720
    refresh_token_expire_days: int = 30
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    seed_admin_email: str = "admin@pipeline.local"
    seed_admin_password: str = "Admin@12345"
    seed_analyst_email: str = "analyst@pipeline.local"
    seed_analyst_password: str = "Analyst@12345"
    seed_viewer_email: str = "viewer@pipeline.local"
    seed_viewer_password: str = "Viewer@12345"
    seed_demo_data: bool = True

    # ---------------------------------------------------------------- ingestion
    ingest_user_agent: str = (
        "ProductIntelligenceBot/1.0 (+https://github.com/Ahmedbakr78; contact: data-team@example.local)"
    )
    respect_robots_txt: bool = True
    request_timeout_seconds: float = 20.0
    max_retries: int = 3
    retry_backoff_seconds: float = 1.5
    requests_per_second: float = 1.0
    requests_per_minute: int = 30
    crawl_delay_fallback_seconds: float = 2.0
    max_concurrent_requests: int = 4
    cache_enabled: bool = True
    cache_ttl_seconds: int = 1800
    respect_terms_whitelist: bool = True

    # ---------------------------------------------------------------- pipeline
    pipeline_batch_size: int = 500
    pipeline_fail_fast: bool = False
    dedupe_similarity_threshold: float = 0.90
    dedupe_blocking_key_length: int = 4
    dedupe_candidate_limit: int = 25
    max_products_per_source: int = 400

    # ---------------------------------------------------------------- runtime
    cache_dir: Path = VAR_DIR / "http-cache"
    log_dir: Path = VAR_DIR / "logs"
    artifacts_dir: Path = VAR_DIR / "artifacts"

    # ---------------------------------------------------------------- validators
    @field_validator("db_schema")
    @classmethod
    def _normalise_schema(cls, value: str) -> str:
        """MySQL has no schemas, everything lives in the connection's database."""
        return value.strip() or "public"

    @field_validator("dedupe_similarity_threshold")
    @classmethod
    def _clamp_threshold(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("dedupe_similarity_threshold must be between 0.0 and 1.0")
        return value

    @field_validator("cors_origins")
    @classmethod
    def _clean_origins(cls, value: str) -> str:
        return ",".join(item.strip().rstrip("/") for item in value.split(",") if item.strip())

    # ---------------------------------------------------------------- helpers
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_testing(self) -> bool:
        return self.app_env == "testing"

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS allow-list as a list (handles the ``*`` wildcard gracefully)."""
        origins = [item for item in self.cors_origins.split(",") if item]
        return origins or ["http://localhost:5173"]

    @property
    def sqlalchemy_url(self) -> str:
        """Active SQLAlchemy URL derived from :attr:`active_database`."""
        if self.active_database == "postgres":
            return self.database_url
        if self.active_database == "mysql":
            if not self.mysql_url:
                raise RuntimeError("ACTIVE_DATABASE=mysql but MYSQL_URL is not configured")
            return self.mysql_url
        return self.database_url

    @property
    def is_sqlite(self) -> bool:
        return self.sqlalchemy_url.startswith("sqlite")

    @property
    def dialect_name(self) -> str:
        url = self.sqlalchemy_url
        for name in ("postgresql", "mysql", "sqlite"):
            if url.startswith(name):
                return name
        return url.split(":", 1)[0]

    def url_for(self, database: str | None = None) -> str:
        """Resolve a SQLAlchemy URL for a named target database.

        ``postgres``/``postgresql`` -> ``DATABASE_URL``
        ``mysql``                   -> ``MYSQL_URL``
        anything else (e.g. a raw URL) is passed through untouched.
        """
        target = (database or self.active_database).strip().lower()
        if target in {"postgres", "postgresql"}:
            return self.database_url
        if target in {"mysql", "mariadb"}:
            if not self.mysql_url:
                raise RuntimeError("MYSQL_URL is required to target MySQL")
            return self.mysql_url
        if target in {"sqlite", "file"}:
            return self.database_url
        return target

    def ensure_directories(self) -> None:
        """Create writable runtime directories (idempotent)."""
        for directory in (VAR_DIR, self.cache_dir, self.log_dir, self.artifacts_dir):
            directory.mkdir(parents=True, exist_ok=True)
        DEFAULT_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton (fast - env parsing happens once)."""
    return Settings()


settings = get_settings()


def reload_settings() -> Settings:
    """Clear the cache and re-read the environment (used by tests and the CLI)."""
    get_settings.cache_clear()
    global settings
    settings = get_settings()
    return settings


def describe_target(database: str | None = None) -> str:
    """Human readable, secret-free description of a database target."""
    url = settings.url_for(database)
    redacted = url
    if "@" in redacted:
        scheme, _, host = redacted.partition("://")
        creds, _, hostpart = host.partition("@")
        redacted = f"{scheme}://***:***@{hostpart}"
    return redacted


def python_path_entries() -> list[str]:
    """Directories that must be importable for Airflow/CLI execution."""
    entries = [str(ROOT_DIR)]
    existing = os.environ.get("PYTHONPATH", "")
    if existing:
        entries.append(existing)
    return entries


__all__: list[str] = [
    "ROOT_DIR",
    "APP_DIR",
    "DB_DIR",
    "DOCS_DIR",
    "FRONTEND_DIR",
    "VAR_DIR",
    "DEFAULT_SQLITE_PATH",
    "Settings",
    "settings",
    "get_settings",
    "reload_settings",
    "describe_target",
    "functools",
    "Any",
    "Field",
]