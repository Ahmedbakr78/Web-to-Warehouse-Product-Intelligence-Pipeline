"""Application-side tables: users, roles, preferences, saved views, alerts, audit log, API keys."""

from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, MediumStr, ShortStr, TimestampMixin, utcnow


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
    theme: Mapped[str] = mapped_column(ShortStr, default="system")  # system | light | dark
    accent: Mapped[str] = mapped_column(ShortStr, default="indigo")
    density: Mapped[str] = mapped_column(ShortStr, default="comfortable")
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    rows_per_page: Mapped[int] = mapped_column(sa.Integer, default=25)
    default_currency: Mapped[str] = mapped_column(ShortStr, default="USD")
    price_change_alert_pct: Mapped[float] = mapped_column(sa.Float, default=5.0)
    email_alerts_enabled: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    weekly_digest_enabled: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    login_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    last_login_at: Mapped[dt.datetime | None] = mapped_column(sa.DateTime(timezone=True))
    last_login_ip: Mapped[str | None] = mapped_column(ShortStr)
    password_changed_at: Mapped[dt.datetime | None] = mapped_column(sa.DateTime(timezone=True))
    two_factor_enabled: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    failed_login_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    locked_until: Mapped[dt.datetime | None] = mapped_column(sa.DateTime(timezone=True))
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
    expires_at: Mapped[dt.datetime | None] = mapped_column(sa.DateTime(timezone=True))
    last_used_at: Mapped[dt.datetime | None] = mapped_column(sa.DateTime(timezone=True))
    usage_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    rate_limit_per_minute: Mapped[int] = mapped_column(sa.Integer, default=120)

    __table_args__ = (
        sa.Index("ix_app_api_key_user", "user_id"),
    )


class AppSavedView(Base, TimestampMixin):
    """User saved filter/sort/column configuration for any list view."""

    __tablename__ = "app_saved_view"

    view_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(sa.Integer, sa.ForeignKey("app_user.user_id", ondelete="CASCADE"))
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

    __table_args__ = (
        sa.Index("ix_app_saved_view_entity", "entity"),
    )


class AppAlertRule(Base, TimestampMixin):
    """User-defined alert (price drop, rating drop, new product in category...)."""

    __tablename__ = "app_alert_rule"

    alert_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("app_user.user_id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(MediumStr, nullable=False)
    metric: Mapped[str] = mapped_column(ShortStr, nullable=False)  # price_change_pct | rating | new_product | dq_failure
    operator: Mapped[str] = mapped_column(ShortStr, nullable=False, default="lt")  # lt|gt|gte|lte|eq
    threshold: Mapped[float] = mapped_column(sa.Float, nullable=False, default=10.0)
    category: Mapped[str | None] = mapped_column(MediumStr)
    source_code: Mapped[str | None] = mapped_column(ShortStr)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    channel: Mapped[str] = mapped_column(ShortStr, default="in_app")  # in_app | email | webhook
    last_triggered_at: Mapped[dt.datetime | None] = mapped_column(sa.DateTime(timezone=True))
    trigger_count: Mapped[int] = mapped_column(sa.Integer, default=0)

    __table_args__ = (
        sa.Index("ix_app_alert_user_active", "user_id", "is_active"),
    )


class AppNotification(Base):
    """In-app notification generated by the pipeline or by alert rules."""

    __tablename__ = "app_notification"

    notification_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(sa.Integer, sa.ForeignKey("app_user.user_id", ondelete="CASCADE"), index=True)
    alert_id: Mapped[int | None] = mapped_column(sa.Integer, sa.ForeignKey("app_alert_rule.alert_id", ondelete="CASCADE"))
    level: Mapped[str] = mapped_column(ShortStr, default="info")  # info | success | warning | critical
    title: Mapped[str] = mapped_column(MediumStr, nullable=False)
    body: Mapped[str | None] = mapped_column(sa.Text)
    entity_type: Mapped[str | None] = mapped_column(ShortStr)
    entity_id: Mapped[str | None] = mapped_column(ShortStr)
    action_url: Mapped[str | None] = mapped_column(sa.String(512))
    is_read: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    __table_args__ = (
        sa.Index("ix_app_notification_user_read", "user_id", "is_read"),
    )


class AppAuditLog(Base):
    """Immutable audit trail for every mutating operation."""

    __tablename__ = "app_audit_log"

    audit_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(sa.Integer, sa.ForeignKey("app_user.user_id", ondelete="SET NULL"), index=True)
    user_email: Mapped[str | None] = mapped_column(MediumStr)
    action: Mapped[str] = mapped_column(ShortStr, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(ShortStr)
    entity_id: Mapped[str | None] = mapped_column(ShortStr)
    status: Mapped[str] = mapped_column(ShortStr, default="success")
    ip_address: Mapped[str | None] = mapped_column(ShortStr)
    user_agent: Mapped[str | None] = mapped_column(ShortStr)
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer)
    details: Mapped[dict | None] = mapped_column(JSONType, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    __table_args__ = (
        sa.Index("ix_app_audit_action_time", "action", "created_at"),
    )


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
        sa.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


__all__ = [
    "AppUser",
    "AppApiKey",
    "AppSavedView",
    "AppAlertRule",
    "AppNotification",
    "AppAuditLog",
    "AppSetting",
]