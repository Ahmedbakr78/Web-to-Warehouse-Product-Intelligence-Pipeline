"""Pydantic request/response models (the public contract of the REST API)."""

from __future__ import annotations

import datetime as dt
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base model that can serialise SQLAlchemy rows directly."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# --------------------------------------------------------------------------------------
# Generic envelopes
# --------------------------------------------------------------------------------------
class Page(BaseModel, Generic[T]):
    """Paginated list response."""

    items: list[T]
    total: int = 0
    page: int = 1
    page_size: int = 25
    pages: int = 0
    has_next: bool = False
    has_prev: bool = False

    @classmethod
    def build(cls, items: list[Any], total: int, page: int, page_size: int) -> Page[Any]:
        pages = max(1, (total + page_size - 1) // page_size)
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
            has_next=page < pages,
            has_prev=page > 1,
        )


class Message(BaseModel):
    """Simple ``{"message": ...}`` response."""

    message: str
    detail: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    database: dict[str, Any]
    sources: list[dict[str, Any]] = Field(default_factory=list)
    timestamp: dt.datetime


# --------------------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=256)
    remember: bool = True


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str
    user: UserRead


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=256)

    @field_validator("new_password")
    @classmethod
    def _strong(cls, value: str) -> str:
        from app.api.security import password_strength

        ok, problems = password_strength(value)
        if not ok:
            raise ValueError("password too weak: " + ", ".join(problems))
        return value


class UserRead(ORMModel):
    user_id: int
    email: str
    full_name: str
    role: str
    job_title: str | None = None
    department: str | None = None
    avatar_color: str | None = None
    timezone: str = "UTC"
    locale: str = "en"
    theme: str = "system"
    accent: str = "indigo"
    density: str = "comfortable"
    is_active: bool = True
    is_verified: bool = False
    rows_per_page: int = 25
    default_currency: str = "USD"
    price_change_alert_pct: float = 5.0
    email_alerts_enabled: bool = False
    weekly_digest_enabled: bool = False
    two_factor_enabled: bool = False
    login_count: int = 0
    last_login_at: dt.datetime | None = None
    created_at: dt.datetime | None = None
    permissions: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    full_name: str | None = None
    job_title: str | None = None
    department: str | None = None
    timezone: str | None = None
    locale: str | None = None
    theme: Literal["system", "light", "dark"] | None = None
    accent: str | None = None
    density: Literal["compact", "comfortable", "spacious"] | None = None
    rows_per_page: int | None = Field(default=None, ge=5, le=500)
    default_currency: str | None = None
    price_change_alert_pct: float | None = Field(default=None, ge=0, le=100)
    email_alerts_enabled: bool | None = None
    weekly_digest_enabled: bool | None = None
    avatar_color: str | None = None
    preferences: dict[str, Any] | None = None


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=128)
    password: str = Field(min_length=10, max_length=256)
    role: Literal["admin", "analyst", "viewer"] = "viewer"
    job_title: str | None = None
    department: str | None = None


class UserStats(BaseModel):
    total_users: int
    active_users: int
    logins_24h: int
    logins_7d: int
    locked_users: int
    api_keys: int
    by_role: dict[str, int] = Field(default_factory=dict)
    top_users: list[dict[str, Any]] = Field(default_factory=list)


class ApiKeyRead(ORMModel):
    key_id: int
    name: str
    prefix: str
    scopes: list[str] | None = None
    is_active: bool
    created_at: dt.datetime
    last_used_at: dt.datetime | None = None
    usage_count: int
    expires_at: dt.datetime | None = None


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=64)


class ApiKeyCreated(ApiKeyRead):
    api_key: str = Field(description="Shown once - store it now.")


# --------------------------------------------------------------------------------------
# Products / analytics
# --------------------------------------------------------------------------------------
class ProductSummary(ORMModel):
    product_id: int
    canonical_name: str
    brand: str | None = None
    category_name: str | None = None
    category_path: str | None = None
    availability: str | None = None
    price: float | None = None
    price_usd: float | None = None
    currency: str | None = None
    rating: float | None = None
    in_stock: bool | None = None
    price_change_pct: float | None = None
    price_change_abs: float | None = None
    is_active: bool = True
    last_seen_at: dt.datetime | None = None
    first_seen_at: dt.datetime | None = None
    observation_count: int | None = None
    product_url: str | None = None
    image_url: str | None = None
    source_code: str | None = None
    match_strategy: str | None = None
    match_score: float | None = None


class ProductDetail(ProductSummary):
    normalized_name: str | None = None
    description: str | None = None
    rating_count: int | None = None
    source_product_id: str | None = None
    fingerprint: str | None = None
    snapshot_id: int | None = None
    run_id: str | None = None
    captured_at: dt.datetime | None = None
    discount_pct: float | None = None
    list_price: float | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)
    changes: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    catalog: list[dict[str, Any]] = Field(default_factory=list)


class PricePoint(ORMModel):
    snapshot_id: int
    product_id: int
    captured_at: dt.datetime
    price: float | None = None
    price_usd: float | None = None
    currency: str
    rating: float | None = None
    availability: str | None = None
    source_code: str
    price_change_abs: float | None = None
    price_change_pct: float | None = None
    is_first_sighting: bool | None = None


class ChangeEvent(ORMModel):
    event_id: int
    product_id: int
    canonical_name: str | None = None
    brand: str | None = None
    category_name: str | None = None
    source_code: str | None = None
    event_type: str
    severity: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    old_category: str | None = None
    new_category: str | None = None
    days_missing: int | None = None
    detected_at: dt.datetime
    full_date: dt.date | None = None


class PriceChangeRead(ORMModel):
    change_id: int
    product_id: int
    canonical_name: str | None = None
    brand: str | None = None
    category_name: str | None = None
    source_code: str | None = None
    previous_price: float | None = None
    new_price: float | None = None
    previous_price_usd: float | None = None
    new_price_usd: float | None = None
    change_abs: float | None = None
    change_pct: float | None = None
    direction: str | None = None
    magnitude_band: str | None = None
    is_significant: bool | None = None
    currency: str | None = None
    detected_at: dt.datetime | None = None
    full_date: dt.date | None = None


class SourceRead(BaseModel):
    code: str
    name: str
    kind: str
    base_url: str
    robots_url: str | None = None
    terms_url: str | None = None
    terms_allowed: bool = True
    robots_respected: bool = True
    rate_limit_per_minute: int
    min_delay_seconds: float
    enabled: bool = True
    supports_paging: bool = False
    description: str = ""
    total_runs: int = 0
    total_records: int = 0
    success_rate_pct: float = 0.0
    avg_duration_seconds: float = 0.0
    last_run_at: dt.datetime | None = None
    products_seen: int | None = None
    observations: int | None = None


class PipelineRunRead(ORMModel):
    run_id: str
    status: str
    trigger: str | None = None
    target_database: str | None = None
    started_at: dt.datetime
    finished_at: dt.datetime | None = None
    duration_ms: int | None = None
    records_extracted: int = 0
    records_valid: int = 0
    records_rejected: int = 0
    records_inserted: int = 0
    records_updated: int = 0
    duplicates_merged: int = 0
    new_products: int = 0
    price_changes: int = 0
    removed_products: int = 0
    catalog_matched: int = 0
    dq_score: float | None = None
    yield_pct: float | None = None
    dag_id: str | None = None
    task_id: str | None = None
    error_message: str | None = None


class PipelineTriggerRequest(BaseModel):
    sources: list[str] | None = Field(default=None, description="Defaults to every enabled source")
    database: str | None = Field(default=None, description="postgres | mysql | sqlite")
    limit_per_source: int | None = Field(default=25, ge=1, le=5000)
    strict: bool = False
    skip_dq: bool = False
    skip_catalog: bool = False
    trigger: str = "api"


class DqRuleRead(ORMModel):
    result_id: int | None = None
    rule_code: str
    rule_name: str | None = None
    dimension: str
    severity: str
    status: str
    observed_value: float | None = None
    expected_value: float | None = None
    records_checked: int = 0
    records_failed: int = 0
    pass_rate_pct: float | None = None
    message: str | None = None
    evaluated_at: dt.datetime | None = None


class CatalogMatchRead(ORMModel):
    match_id: int
    run_id: str | None = None
    catalog_sku: str
    catalog_name: str | None = None
    catalog_brand: str | None = None
    catalog_category: str | None = None
    catalog_price: float | None = None
    supplier: str | None = None
    product_id: int | None = None
    scraped_name: str | None = None
    scraped_brand: str | None = None
    scraped_category: str | None = None
    scraped_price_usd: float | None = None
    price_gap_abs: float | None = None
    price_gap_pct: float | None = None
    match_status: str
    match_strategy: str | None = None
    similarity_score: float | None = None
    category_match: bool | None = None
    brand_match: bool | None = None
    is_price_mismatch: bool = False
    matched_at: dt.datetime | None = None


class SavedViewRead(ORMModel):
    view_id: int
    name: str
    entity: str
    description: str | None = None
    filters: dict[str, Any] | None = None
    sort_by: str | None = None
    sort_dir: str = "desc"
    visible_columns: list[str] | None = None
    is_shared: bool = False
    is_favorite: bool = False
    use_count: int = 0
    user_id: int | None = None


class SavedViewCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    entity: Literal["products", "changes", "runs", "quality", "catalog", "sources"]
    description: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    sort_by: str | None = None
    sort_dir: Literal["asc", "desc"] = "desc"
    visible_columns: list[str] = Field(default_factory=list)
    is_shared: bool = False
    is_favorite: bool = False


class AlertRuleRead(ORMModel):
    alert_id: int
    name: str
    metric: str
    operator: str
    threshold: float
    category: str | None = None
    source_code: str | None = None
    is_active: bool = True
    channel: str = "in_app"
    last_triggered_at: dt.datetime | None = None
    trigger_count: int = 0
    user_id: int | None = None


class AlertRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    metric: Literal["price_change_pct", "rating", "new_product", "dq_failure", "stock_out"]
    operator: Literal["lt", "gt", "lte", "gte", "eq"] = "lt"
    threshold: float = 10.0
    category: str | None = None
    source_code: str | None = None
    channel: Literal["in_app", "email", "webhook"] = "in_app"
    is_active: bool = True


class NotificationRead(ORMModel):
    notification_id: int
    level: str
    title: str
    body: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    action_url: str | None = None
    is_read: bool = False
    created_at: dt.datetime


class SettingRead(ORMModel):
    key: str
    value: str | None = None
    value_type: str = "string"
    category: str = "general"
    description: str | None = None
    is_public: bool = False
    updated_at: dt.datetime | None = None


class SettingUpdate(BaseModel):
    value: str
    value_type: Literal["string", "number", "boolean", "json"] = "string"


class AuditLogRead(ORMModel):
    audit_id: int
    user_id: int | None = None
    user_email: str | None = None
    action: str
    entity_type: str | None = None
    entity_id: str | None = None
    status: str = "success"
    ip_address: str | None = None
    duration_ms: int | None = None
    created_at: dt.datetime


class HttpLogRead(ORMModel):
    log_id: int
    run_id: str | None = None
    source_code: str | None = None
    method: str
    url: str
    host: str | None = None
    status_code: int | None = None
    elapsed_ms: float | None = None
    response_bytes: int | None = None
    robots_allowed: bool | None = None
    robots_rule: str | None = None
    from_cache: bool = False
    retry_count: int = 0
    error: str | None = None
    requested_at: dt.datetime


class QueryRequest(BaseModel):
    """Read-only SQL console (SELECT / WITH / EXPLAIN only)."""

    sql: str = Field(min_length=3, max_length=20000)
    limit: int = Field(default=200, ge=1, le=5000)

    @field_validator("sql")
    @classmethod
    def _readonly(cls, value: str) -> str:
        stripped = value.strip().rstrip(";").lower()
        allowed = ("select ", "with ", "explain ")
        if not stripped.startswith(allowed):
            raise ValueError("only SELECT / WITH / EXPLAIN statements are allowed")
        forbidden = (
            "insert ",
            "update ",
            "delete ",
            "drop ",
            "alter ",
            "create ",
            "truncate ",
            "grant ",
            "revoke ",
            "commit ",
            "rollback ",
            "; --",
            "/*",
        )
        if any(token in stripped for token in forbidden):
            raise ValueError("statement contains a write or multiple statement")
        return value


class QueryResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    duration_ms: float
    truncated: bool = False


TokenResponse.model_rebuild()

__all__ = [name for name in dir() if name[0].isupper()] + [
    "ORMModel",
    "Page",
    "Message",
    "ErrorResponse",
    "HealthResponse",
    "LoginRequest",
    "TokenResponse",
    "RefreshRequest",
    "PasswordChangeRequest",
    "UserRead",
    "UserUpdate",
    "UserCreate",
    "UserStats",
    "ApiKeyRead",
    "ApiKeyCreate",
    "ApiKeyCreated",
    "ProductSummary",
    "ProductDetail",
    "PricePoint",
    "ChangeEvent",
    "PriceChangeRead",
    "SourceRead",
    "PipelineRunRead",
    "PipelineTriggerRequest",
    "DqRuleRead",
    "CatalogMatchRead",
    "SavedViewRead",
    "SavedViewCreate",
    "AlertRuleRead",
    "AlertRuleCreate",
    "NotificationRead",
    "SettingRead",
    "SettingUpdate",
    "AuditLogRead",
    "HttpLogRead",
    "QueryRequest",
    "QueryResponse",
]
