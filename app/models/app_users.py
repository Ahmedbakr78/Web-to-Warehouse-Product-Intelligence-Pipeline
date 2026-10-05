"""Application-side tables: users, roles, preferences, saved views, alerts, audit log, API keys."""

from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, MediumStr, ShortStr, TimestampMixin, UTCDateTime, utcnow


class AppUser(Base, TimestampMixin):
    """Dashboard account with a role that maps onto an API permission set."""

    __tablename__ = "app_user"

    user_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(MediumStr, nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(MediumStr, nullable=False)
    hashed_password: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    role: Mapped[str] = mapped_column(ShortStr, nullable=False, default="viewer")
    job_title: Mapped[str | None] = mapped_column(ShortStr)
    department: Mapped[str | None] = mapped_column(ShortStr)
    avatar_color: Mapped[str | None] = mapped_column(ShortStr, default="#6366f1")
    timezone: Mapped[str] = mapped_column(ShortStr, default="UTC")
    locale: Mapped[str] = mapped_column(ShortStr, default="en")
    # Appearance preferences. `theme` accepts five values (see THEME_VALUES below);
    # the other three axes are independent of it, so a user can have a dark palette
    # with compact density and a large font scale at the same time.
    theme: Mapped[str] = mapped_column(ShortStr, default="system")
    accent: Mapped[str] = mapped_column(ShortStr, default="indigo")
    density: Mapped[str] = mapped_column(ShortStr, default="comfortable")
    motion: Mapped[str] = mapped_column(ShortStr, default="full")
    direction: Mapped[str] = mapped_column(ShortStr, default="ltr")
    font_scale: Mapped[str] = mapped_column(ShortStr, default="md")
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    rows_per_page: Mapped[int] = mapped_column(sa.Integer, default=25)
    default_currency: Mapped[str] = mapped_column(ShortStr, default="USD")
    price_change_alert_pct: Mapped[float] = mapped_column(sa.Float, default=5.0)
    email_alerts_enabled: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    weekly_digest_enabled: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    login_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    last_login_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    last_login_ip: Mapped[str | None] = mapped_column(ShortStr)
    password_changed_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    two_factor_enabled: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    failed_login_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    locked_until: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    preferences: Mapped[dict | None] = mapped_column(JSONType, default=dict)

    __table_args__ = (
        sa.Index("ix_app_user_role", "role"),
        sa.Index("ix_app_user_active", "is_active"),
    )


class AppApiKey(Base, TimestampMixin):
    """Machine-to-machine key (scoped, hashed at rest, revocable)."""

    __tablename__ = "app_api_key"

    key_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("app_user.user_id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(ShortStr, nullable=False)
    prefix: Mapped[str] = mapped_column(ShortStr, nullable=False, index=True)
    hashed_key: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    scopes: Mapped[list | None] = mapped_column(JSONType, default=list)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    expires_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    last_used_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    usage_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    rate_limit_per_minute: Mapped[int] = mapped_column(sa.Integer, default=120)

    __table_args__ = (sa.Index("ix_app_api_key_user", "user_id"),)


class AppSavedView(Base, TimestampMixin):
    """User saved filter/sort/column configuration for any list view."""

    __tablename__ = "app_saved_view"

    view_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        sa.Integer, sa.ForeignKey("app_user.user_id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(MediumStr, nullable=False)
    entity: Mapped[str] = mapped_column(ShortStr, nullable=False)
    description: Mapped[str | None] = mapped_column(MediumStr)
    filters: Mapped[dict | None] = mapped_column(JSONType, default=dict)
    sort_by: Mapped[str | None] = mapped_column(ShortStr)
    sort_dir: Mapped[str] = mapped_column(ShortStr, default="desc")
    visible_columns: Mapped[list | None] = mapped_column(JSONType, default=list)
    is_shared: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    is_favorite: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    is_default: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    use_count: Mapped[int] = mapped_column(sa.Integer, default=0)

    __table_args__ = (sa.Index("ix_app_saved_view_entity", "entity"),)


class AppAlertRule(Base, TimestampMixin):
    """User-defined alert (price drop, rating drop, new product in category...)."""

    __tablename__ = "app_alert_rule"

    alert_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("app_user.user_id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(MediumStr, nullable=False)
    metric: Mapped[str] = mapped_column(
        ShortStr, nullable=False
    )  # price_change_pct | rating | new_product | dq_failure
    operator: Mapped[str] = mapped_column(ShortStr, nullable=False, default="lt")  # lt|gt|gte|lte|eq
    threshold: Mapped[float] = mapped_column(sa.Float, nullable=False, default=10.0)
    category: Mapped[str | None] = mapped_column(MediumStr)
    source_code: Mapped[str | None] = mapped_column(ShortStr)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    channel: Mapped[str] = mapped_column(ShortStr, default="in_app")  # in_app | email | webhook
    last_triggered_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    trigger_count: Mapped[int] = mapped_column(sa.Integer, default=0)

    __table_args__ = (sa.Index("ix_app_alert_user_active", "user_id", "is_active"),)


class AppNotification(Base):
    """In-app notification generated by the pipeline or by alert rules."""

    __tablename__ = "app_notification"

    notification_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        sa.Integer, sa.ForeignKey("app_user.user_id", ondelete="CASCADE"), index=True
    )
    alert_id: Mapped[int | None] = mapped_column(
        sa.Integer, sa.ForeignKey("app_alert_rule.alert_id", ondelete="CASCADE")
    )
    level: Mapped[str] = mapped_column(ShortStr, default="info")  # info | success | warning | critical
    title: Mapped[str] = mapped_column(MediumStr, nullable=False)
    body: Mapped[str | None] = mapped_column(sa.Text)
    entity_type: Mapped[str | None] = mapped_column(ShortStr)
    entity_id: Mapped[str | None] = mapped_column(ShortStr)
    action_url: Mapped[str | None] = mapped_column(sa.String(512))
    is_read: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False, index=True)

    __table_args__ = (sa.Index("ix_app_notification_user_read", "user_id", "is_read"),)


class AppWebhook(Base, TimestampMixin):
    """Outbound webhook subscription with a per-subscription signing secret."""

    __tablename__ = "app_webhook"

    webhook_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("app_user.user_id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(MediumStr, nullable=False)
    target_url: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    secret: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    events: Mapped[list | None] = mapped_column(JSONType, default=list)  # subscribed event names
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    description: Mapped[str | None] = mapped_column(sa.Text)
    headers: Mapped[dict | None] = mapped_column(JSONType, default=dict)  # extra static headers
    timeout_seconds: Mapped[int] = mapped_column(sa.Integer, default=10)
    max_attempts: Mapped[int] = mapped_column(sa.Integer, default=3)
    success_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    failure_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    consecutive_failures: Mapped[int] = mapped_column(sa.Integer, default=0)
    last_status_code: Mapped[int | None] = mapped_column(sa.Integer)
    last_error: Mapped[str | None] = mapped_column(sa.Text)
    last_triggered_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    disabled_reason: Mapped[str | None] = mapped_column(ShortStr)

    __table_args__ = (
        sa.Index("ix_app_webhook_user_active", "user_id", "is_active"),
        sa.Index("ix_app_webhook_target", "target_url"),
    )


class AppWebhookDelivery(Base):
    """One delivery attempt (or attempt series) for a webhook event."""

    __tablename__ = "app_webhook_delivery"

    delivery_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    webhook_id: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("app_webhook.webhook_id", ondelete="CASCADE")
    )
    event: Mapped[str] = mapped_column(ShortStr, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(ShortStr, default="pending")  # pending|success|failed
    attempts: Mapped[int] = mapped_column(sa.Integer, default=0)
    status_code: Mapped[int | None] = mapped_column(sa.Integer)
    response_excerpt: Mapped[str | None] = mapped_column(sa.Text)
    error: Mapped[str | None] = mapped_column(sa.Text)
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer)
    next_retry_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), index=True)
    delivered_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False, index=True)

    __table_args__ = (
        sa.Index("ix_app_webhook_delivery_hook", "webhook_id", "created_at"),
        sa.Index("ix_app_webhook_delivery_status", "status", "next_retry_at"),
    )


class AppAuditLog(Base):
    """Immutable audit trail for every mutating operation."""

    __tablename__ = "app_audit_log"

    audit_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        sa.Integer, sa.ForeignKey("app_user.user_id", ondelete="SET NULL"), index=True
    )
    user_email: Mapped[str | None] = mapped_column(MediumStr)
    action: Mapped[str] = mapped_column(ShortStr, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(ShortStr)
    entity_id: Mapped[str | None] = mapped_column(ShortStr)
    status: Mapped[str] = mapped_column(ShortStr, default="success")
    ip_address: Mapped[str | None] = mapped_column(ShortStr)
    user_agent: Mapped[str | None] = mapped_column(ShortStr)
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer)
    details: Mapped[dict | None] = mapped_column(JSONType, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False, index=True)

    __table_args__ = (sa.Index("ix_app_audit_action_time", "action", "created_at"),)


class AppSetting(Base):
    """Global key/value settings edited from the admin settings screen."""

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(ShortStr, primary_key=True)
    value: Mapped[str | None] = mapped_column(sa.Text)
    value_type: Mapped[str] = mapped_column(ShortStr, default="string")
    category: Mapped[str] = mapped_column(ShortStr, default="general")
    description: Mapped[str | None] = mapped_column(MediumStr)
    is_public: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    updated_by: Mapped[str | None] = mapped_column(MediumStr)
    updated_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )


class AppJob(Base, TimestampMixin):
    """A unit of background work with a durable lease, progress and retry state.

    Replaces in-process ``BackgroundTasks`` for anything that can take longer than
    a request: the row survives a restart, ``lease_expires_at`` lets another worker
    reclaim a job whose owner died, and ``attempt``/``max_attempts`` make retries
    explicit rather than best-effort.
    """

    __tablename__ = "app_job"

    job_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    #: Caller-facing handle: a short opaque id used in URLs and the UI.
    job_key: Mapped[str] = mapped_column(ShortStr, nullable=False, unique=True)
    #: What to run: `pipeline_run`, `backfill`, `export`, `forecast` or a webhook delivery series.
    job_type: Mapped[str] = mapped_column(ShortStr, nullable=False, index=True)
    #: queued | running | succeeded | failed | cancelled
    status: Mapped[str] = mapped_column(ShortStr, default="queued", nullable=False, index=True)
    #: Constructor keyword arguments, replayed by the worker.
    payload: Mapped[dict | None] = mapped_column(JSONType, default=dict)
    #: Public progress, 0-100, plus a short human-readable stage label.
    progress_pct: Mapped[int] = mapped_column(sa.Integer, default=0)
    stage: Mapped[str | None] = mapped_column(ShortStr)
    result: Mapped[dict | None] = mapped_column(JSONType, default=dict)
    error: Mapped[str | None] = mapped_column(sa.Text)

    requested_by: Mapped[int | None] = mapped_column(
        sa.Integer, sa.ForeignKey("app_user.user_id", ondelete="SET NULL"), index=True
    )
    requested_by_email: Mapped[str | None] = mapped_column(ShortStr)

    attempt: Mapped[int] = mapped_column(sa.Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(sa.Integer, default=3)
    #: Set while a worker holds the job. A worker that stops heartbeating loses the
    #: lease and another worker may claim it.
    lease_owner: Mapped[str | None] = mapped_column(ShortStr, index=True)
    lease_expires_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    heartbeat_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())

    queued_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False, index=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), index=True)
    cancel_requested: Mapped[bool] = mapped_column(sa.Boolean, default=False)

    __table_args__ = (
        sa.Index("ix_app_job_status_queued", "status", "queued_at"),
        sa.Index("ix_app_job_type_requested", "job_type", "requested_by"),
    )


class AppJobEvent(Base):
    """An append-only progress line for a job, streamed to the UI over SSE."""

    __tablename__ = "app_job_event"

    event_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("app_job.job_id", ondelete="CASCADE"), index=True
    )
    #: info | progress | warning | error
    level: Mapped[str] = mapped_column(ShortStr, default="info")
    stage: Mapped[str | None] = mapped_column(ShortStr)
    message: Mapped[str] = mapped_column(sa.Text, nullable=False)
    progress_pct: Mapped[int | None] = mapped_column(sa.Integer)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False, index=True)

    __table_args__ = (sa.Index("ix_app_job_event_job", "job_id", "event_id"),)


__all__ = [
    "AppUser",
    "AppApiKey",
    "AppSavedView",
    "AppAlertRule",
    "AppNotification",
    "AppAuditLog",
    "AppSetting",
    "AppWebhook",
    "AppWebhookDelivery",
    "AppJob",
    "AppJobEvent",
]
