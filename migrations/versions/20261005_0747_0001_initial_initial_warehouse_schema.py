"""Initial warehouse schema: 28 tables.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-05 07:47:22.835903

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.models.base

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create every warehouse table.

    Also applies the 20 analytical views at the end. They are not in the ORM -
    `db/views.sql` is their source of truth, applied by
    `app.etl.bootstrap.apply_views()` - and the whole analytics layer reads through
    them, so a migration that created the tables without the views would leave the
    application with a schema it cannot query.
    """
    op.create_table(
        "app_setting",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("value_type", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.String(length=512), nullable=True),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_setting")),
    )
    op.create_table(
        "app_user",
        sa.Column("user_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=512), nullable=False),
        sa.Column("full_name", sa.String(length=512), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=128), nullable=False),
        sa.Column("job_title", sa.String(length=128), nullable=True),
        sa.Column("department", sa.String(length=128), nullable=True),
        sa.Column("avatar_color", sa.String(length=128), nullable=True),
        sa.Column("timezone", sa.String(length=128), nullable=False),
        sa.Column("locale", sa.String(length=128), nullable=False),
        sa.Column("theme", sa.String(length=128), nullable=False),
        sa.Column("accent", sa.String(length=128), nullable=False),
        sa.Column("density", sa.String(length=128), nullable=False),
        sa.Column("motion", sa.String(length=128), nullable=False),
        sa.Column("direction", sa.String(length=128), nullable=False),
        sa.Column("font_scale", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("rows_per_page", sa.Integer(), nullable=False),
        sa.Column("default_currency", sa.String(length=128), nullable=False),
        sa.Column("price_change_alert_pct", sa.Float(), nullable=False),
        sa.Column("email_alerts_enabled", sa.Boolean(), nullable=False),
        sa.Column("weekly_digest_enabled", sa.Boolean(), nullable=False),
        sa.Column("login_count", sa.Integer(), nullable=False),
        sa.Column("last_login_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("last_login_ip", sa.String(length=128), nullable=True),
        sa.Column("password_changed_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("two_factor_enabled", sa.Boolean(), nullable=False),
        sa.Column("totp_secret", sa.String(length=255), nullable=True),
        sa.Column("recovery_codes", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("two_factor_enrolled_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("failed_login_count", sa.Integer(), nullable=False),
        sa.Column("locked_until", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("preferences", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_app_user")),
    )
    with op.batch_alter_table("app_user", schema=None) as batch_op:
        batch_op.create_index("ix_app_user_active", ["is_active"], unique=False)
        batch_op.create_index(batch_op.f("ix_app_user_email"), ["email"], unique=True)
        batch_op.create_index("ix_app_user_role", ["role"], unique=False)

    op.create_table(
        "catalog_product",
        sa.Column("sku", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=True),
        sa.Column("brand", sa.String(length=128), nullable=True),
        sa.Column("category", sa.String(length=512), nullable=True),
        sa.Column("supplier", sa.String(length=128), nullable=True),
        sa.Column("cost_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("list_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("currency", sa.String(length=128), nullable=False),
        sa.Column("qty_on_hand", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=128), nullable=False),
        sa.Column("product_url", sa.String(length=2048), nullable=True),
        sa.Column("image_url", sa.String(length=2048), nullable=True),
        sa.Column("attributes", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("sku", name=op.f("pk_catalog_product")),
    )
    with op.batch_alter_table("catalog_product", schema=None) as batch_op:
        batch_op.create_index("ix_catalog_product_brand", ["brand"], unique=False)
        batch_op.create_index("ix_catalog_product_category", ["category"], unique=False)
        batch_op.create_index("ix_catalog_product_status", ["status"], unique=False)

    op.create_table(
        "dim_category",
        sa.Column("category_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=True),
        sa.Column("source_category_raw", sa.String(length=512), nullable=True),
        sa.Column("product_count", sa.Integer(), nullable=False),
        sa.Column("avg_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["dim_category.category_id"], name=op.f("fk_dim_category_parent_id_dim_category")
        ),
        sa.PrimaryKeyConstraint("category_id", name=op.f("pk_dim_category")),
        sa.UniqueConstraint("slug", name=op.f("uq_dim_category_slug")),
    )
    with op.batch_alter_table("dim_category", schema=None) as batch_op:
        batch_op.create_index("ix_dim_category_name", ["name"], unique=False)
        batch_op.create_index("ix_dim_category_parent", ["parent_id"], unique=False)

    op.create_table(
        "dim_currency",
        sa.Column("currency_code", sa.String(length=128), nullable=False),
        sa.Column("currency_name", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=8), nullable=True),
        sa.Column("rate_to_usd", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("rate_source", sa.String(length=128), nullable=True),
        sa.Column("as_of", sa.Date(), nullable=True),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("currency_code", name=op.f("pk_dim_currency")),
    )
    op.create_table(
        "dim_date",
        sa.Column("date_id", sa.Integer(), nullable=False),
        sa.Column("full_date", sa.Date(), nullable=False),
        sa.Column("year", sa.SmallInteger(), nullable=False),
        sa.Column("quarter", sa.SmallInteger(), nullable=False),
        sa.Column("month", sa.SmallInteger(), nullable=False),
        sa.Column("day", sa.SmallInteger(), nullable=False),
        sa.Column("month_name", sa.String(length=128), nullable=True),
        sa.Column("day_name", sa.String(length=128), nullable=True),
        sa.Column("week_of_year", sa.SmallInteger(), nullable=True),
        sa.Column("is_weekend", sa.Boolean(), nullable=False),
        sa.Column("is_month_start", sa.Boolean(), nullable=False),
        sa.Column("is_month_end", sa.Boolean(), nullable=False),
        sa.Column("iso_week", sa.SmallInteger(), nullable=True),
        sa.PrimaryKeyConstraint("date_id", name=op.f("pk_dim_date")),
        sa.UniqueConstraint("full_date", name=op.f("uq_dim_date_full_date")),
    )
    with op.batch_alter_table("dim_date", schema=None) as batch_op:
        batch_op.create_index("ix_dim_date_year_month", ["year", "month"], unique=False)

    op.create_table(
        "dim_source",
        sa.Column("source_code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("kind", sa.String(length=128), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=False),
        sa.Column("robots_url", sa.String(length=2048), nullable=True),
        sa.Column("terms_url", sa.String(length=2048), nullable=True),
        sa.Column("license_note", sa.Text(), nullable=True),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=False),
        sa.Column("min_delay_seconds", sa.Float(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("terms_allowed", sa.Boolean(), nullable=False),
        sa.Column("robots_checked_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("last_run_id", sa.String(length=128), nullable=True),
        sa.Column("last_run_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("total_records", sa.BigInteger(), nullable=False),
        sa.Column("total_runs", sa.Integer(), nullable=False),
        sa.Column("success_rate_pct", sa.Float(), nullable=False),
        sa.Column("avg_duration_seconds", sa.Float(), nullable=False),
        sa.Column("config", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source_code", name=op.f("pk_dim_source")),
    )
    with op.batch_alter_table("dim_source", schema=None) as batch_op:
        batch_op.create_index("ix_dim_source_enabled", ["enabled"], unique=False)
        batch_op.create_index("ix_dim_source_kind", ["kind"], unique=False)

    op.create_table(
        "etl_run",
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("run_key", sa.String(length=128), nullable=True),
        sa.Column("pipeline", sa.String(length=128), nullable=False),
        sa.Column("target_database", sa.String(length=128), nullable=False),
        sa.Column("dag_id", sa.String(length=128), nullable=True),
        sa.Column("task_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=128), nullable=False),
        sa.Column("trigger", sa.String(length=128), nullable=False),
        sa.Column("started_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("finished_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("records_extracted", sa.Integer(), nullable=False),
        sa.Column("records_valid", sa.Integer(), nullable=False),
        sa.Column("records_rejected", sa.Integer(), nullable=False),
        sa.Column("records_inserted", sa.Integer(), nullable=False),
        sa.Column("records_updated", sa.Integer(), nullable=False),
        sa.Column("duplicates_merged", sa.Integer(), nullable=False),
        sa.Column("new_products", sa.Integer(), nullable=False),
        sa.Column("price_changes", sa.Integer(), nullable=False),
        sa.Column("removed_products", sa.Integer(), nullable=False),
        sa.Column("catalog_matched", sa.Integer(), nullable=False),
        sa.Column("dq_passed", sa.Integer(), nullable=False),
        sa.Column("dq_failed", sa.Integer(), nullable=False),
        sa.Column("dq_score", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("warnings", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("params", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("run_id", name=op.f("pk_etl_run")),
    )
    with op.batch_alter_table("etl_run", schema=None) as batch_op:
        batch_op.create_index("ix_etl_run_status_started", ["status", "started_at"], unique=False)
        batch_op.create_index("ix_etl_run_target", ["target_database"], unique=False)
        batch_op.create_index("ix_etl_run_trigger", ["trigger"], unique=False)

    op.create_table(
        "ingestion_http_log",
        sa.Column("log_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=True),
        sa.Column("source_code", sa.String(length=128), nullable=True),
        sa.Column("method", sa.String(length=128), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("host", sa.String(length=128), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("elapsed_ms", sa.Float(), nullable=True),
        sa.Column("response_bytes", sa.Integer(), nullable=True),
        sa.Column("robots_allowed", sa.Boolean(), nullable=True),
        sa.Column("robots_rule", sa.String(length=128), nullable=True),
        sa.Column("from_cache", sa.Boolean(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("requested_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("log_id", name=op.f("pk_ingestion_http_log")),
    )
    with op.batch_alter_table("ingestion_http_log", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_ingestion_http_log_requested_at"), ["requested_at"], unique=False
        )
        batch_op.create_index("ix_ingestion_http_log_run_host", ["run_id", "host"], unique=False)
        batch_op.create_index(batch_op.f("ix_ingestion_http_log_run_id"), ["run_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_ingestion_http_log_source_code"), ["source_code"], unique=False)

    op.create_table(
        "stg_raw_observation",
        sa.Column("observation_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=True),
        sa.Column("source_code", sa.String(length=128), nullable=False),
        sa.Column("source_product_id", sa.String(length=128), nullable=True),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("raw_name", sa.Text(), nullable=True),
        sa.Column("raw_category", sa.String(length=512), nullable=True),
        sa.Column("raw_price_text", sa.String(length=128), nullable=True),
        sa.Column("raw_currency", sa.String(length=128), nullable=True),
        sa.Column("raw_rating_text", sa.String(length=128), nullable=True),
        sa.Column("raw_availability", sa.String(length=128), nullable=True),
        sa.Column("raw_payload", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("payload_hash", sa.String(length=128), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("is_valid", sa.Boolean(), nullable=False),
        sa.Column("reject_reason", sa.String(length=512), nullable=True),
        sa.Column("fetched_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("landed_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("observation_id", name=op.f("pk_stg_raw_observation")),
    )
    with op.batch_alter_table("stg_raw_observation", schema=None) as batch_op:
        batch_op.create_index("ix_stg_raw_observation_landed", ["landed_at"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_stg_raw_observation_payload_hash"), ["payload_hash"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_stg_raw_observation_run_id"), ["run_id"], unique=False)
        batch_op.create_index("ix_stg_raw_observation_run_valid", ["run_id", "is_valid"], unique=False)
        batch_op.create_index(batch_op.f("ix_stg_raw_observation_source_code"), ["source_code"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_stg_raw_observation_source_product_id"), ["source_product_id"], unique=False
        )

    op.create_table(
        "sync_state",
        sa.Column("source_code", sa.String(length=128), nullable=False),
        sa.Column("last_run_id", sa.String(length=128), nullable=True),
        sa.Column("last_success_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("cursor_value", sa.String(length=512), nullable=True),
        sa.Column("cursor_json", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("total_extracted", sa.BigInteger(), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=128), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("source_code", name=op.f("pk_sync_state")),
    )
    with op.batch_alter_table("sync_state", schema=None) as batch_op:
        batch_op.create_index("ix_sync_state_status", ["status"], unique=False)

    op.create_table(
        "agg_category_daily",
        sa.Column("agg_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("source_code", sa.String(length=128), nullable=True),
        sa.Column("product_count", sa.Integer(), nullable=False),
        sa.Column("new_product_count", sa.Integer(), nullable=False),
        sa.Column("removed_product_count", sa.Integer(), nullable=False),
        sa.Column("avg_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("median_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("min_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("max_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("avg_rating", sa.Float(), nullable=True),
        sa.Column("price_change_count", sa.Integer(), nullable=False),
        sa.Column("avg_price_change_pct", sa.Float(), nullable=True),
        sa.Column("computed_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["dim_category.category_id"],
            name=op.f("fk_agg_category_daily_category_id_dim_category"),
        ),
        sa.ForeignKeyConstraint(
            ["date_id"], ["dim_date.date_id"], name=op.f("fk_agg_category_daily_date_id_dim_date")
        ),
        sa.PrimaryKeyConstraint("agg_id", name=op.f("pk_agg_category_daily")),
        sa.UniqueConstraint("date_id", "category_id", "source_code", name="uq_agg_cat_date_cat_source"),
    )
    with op.batch_alter_table("agg_category_daily", schema=None) as batch_op:
        batch_op.create_index("ix_agg_cat_date", ["date_id"], unique=False)

    op.create_table(
        "app_alert_rule",
        sa.Column("alert_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("metric", sa.String(length=128), nullable=False),
        sa.Column("operator", sa.String(length=128), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("category", sa.String(length=512), nullable=True),
        sa.Column("source_code", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("channel", sa.String(length=128), nullable=False),
        sa.Column("last_triggered_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("trigger_count", sa.Integer(), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.user_id"],
            name=op.f("fk_app_alert_rule_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("alert_id", name=op.f("pk_app_alert_rule")),
    )
    with op.batch_alter_table("app_alert_rule", schema=None) as batch_op:
        batch_op.create_index("ix_app_alert_user_active", ["user_id", "is_active"], unique=False)

    op.create_table(
        "app_api_key",
        sa.Column("key_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("prefix", sa.String(length=128), nullable=False),
        sa.Column("hashed_key", sa.String(length=255), nullable=False),
        sa.Column("scopes", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("expires_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.user_id"],
            name=op.f("fk_app_api_key_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("key_id", name=op.f("pk_app_api_key")),
    )
    with op.batch_alter_table("app_api_key", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_app_api_key_prefix"), ["prefix"], unique=False)
        batch_op.create_index("ix_app_api_key_user", ["user_id"], unique=False)

    op.create_table(
        "app_audit_log",
        sa.Column("audit_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("user_email", sa.String(length=512), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=128), nullable=True),
        sa.Column("entity_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=128), nullable=False),
        sa.Column("ip_address", sa.String(length=128), nullable=True),
        sa.Column("user_agent", sa.String(length=128), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.user_id"],
            name=op.f("fk_app_audit_log_user_id_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("audit_id", name=op.f("pk_app_audit_log")),
    )
    with op.batch_alter_table("app_audit_log", schema=None) as batch_op:
        batch_op.create_index("ix_app_audit_action_time", ["action", "created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_app_audit_log_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_app_audit_log_user_id"), ["user_id"], unique=False)

    op.create_table(
        "app_job",
        sa.Column("job_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_key", sa.String(length=128), nullable=False),
        sa.Column("job_type", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("progress_pct", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=128), nullable=True),
        sa.Column("result", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.Integer(), nullable=True),
        sa.Column("requested_by_email", sa.String(length=128), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("queued_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("started_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("finished_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["app_user.user_id"],
            name=op.f("fk_app_job_requested_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("job_id", name=op.f("pk_app_job")),
        sa.UniqueConstraint("job_key", name=op.f("uq_app_job_job_key")),
    )
    with op.batch_alter_table("app_job", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_app_job_finished_at"), ["finished_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_app_job_job_type"), ["job_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_app_job_lease_owner"), ["lease_owner"], unique=False)
        batch_op.create_index(batch_op.f("ix_app_job_queued_at"), ["queued_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_app_job_requested_by"), ["requested_by"], unique=False)
        batch_op.create_index(batch_op.f("ix_app_job_status"), ["status"], unique=False)
        batch_op.create_index("ix_app_job_status_queued", ["status", "queued_at"], unique=False)
        batch_op.create_index("ix_app_job_type_requested", ["job_type", "requested_by"], unique=False)

    op.create_table(
        "app_saved_view",
        sa.Column("view_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("entity", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("filters", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("sort_by", sa.String(length=128), nullable=True),
        sa.Column("sort_dir", sa.String(length=128), nullable=False),
        sa.Column("visible_columns", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("is_shared", sa.Boolean(), nullable=False),
        sa.Column("is_favorite", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("use_count", sa.Integer(), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.user_id"],
            name=op.f("fk_app_saved_view_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("view_id", name=op.f("pk_app_saved_view")),
    )
    with op.batch_alter_table("app_saved_view", schema=None) as batch_op:
        batch_op.create_index("ix_app_saved_view_entity", ["entity"], unique=False)

    op.create_table(
        "app_session",
        sa.Column("session_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_key", sa.String(length=128), nullable=False),
        sa.Column("refresh_hash", sa.String(length=128), nullable=True),
        sa.Column("ip_address", sa.String(length=128), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("expires_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=128), nullable=True),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.user_id"],
            name=op.f("fk_app_session_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("session_id", name=op.f("pk_app_session")),
        sa.UniqueConstraint("session_key", name=op.f("uq_app_session_session_key")),
    )
    with op.batch_alter_table("app_session", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_app_session_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_app_session_expires_at"), ["expires_at"], unique=False)
        batch_op.create_index("ix_app_session_expiry", ["expires_at"], unique=False)
        batch_op.create_index("ix_app_session_user_active", ["user_id", "revoked_at"], unique=False)

    op.create_table(
        "app_webhook",
        sa.Column("webhook_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("target_url", sa.String(length=512), nullable=False),
        sa.Column("secret", sa.String(length=128), nullable=False),
        sa.Column("events", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("headers", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_triggered_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("disabled_reason", sa.String(length=128), nullable=True),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.user_id"],
            name=op.f("fk_app_webhook_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("webhook_id", name=op.f("pk_app_webhook")),
    )
    with op.batch_alter_table("app_webhook", schema=None) as batch_op:
        batch_op.create_index("ix_app_webhook_target", ["target_url"], unique=False)
        batch_op.create_index("ix_app_webhook_user_active", ["user_id", "is_active"], unique=False)

    op.create_table(
        "dim_product",
        sa.Column("product_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_product_id", sa.String(length=128), nullable=True),
        sa.Column("source_code", sa.String(length=128), nullable=True),
        sa.Column("canonical_name", sa.String(length=512), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(length=512), nullable=True),
        sa.Column("brand", sa.String(length=128), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("product_url", sa.String(length=2048), nullable=True),
        sa.Column("image_url", sa.String(length=2048), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("currency", sa.String(length=128), nullable=True),
        sa.Column("current_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("previous_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("current_rating", sa.Float(), nullable=True),
        sa.Column("rating_count", sa.Integer(), nullable=True),
        sa.Column("availability", sa.String(length=128), nullable=True),
        sa.Column("fingerprint", sa.String(length=128), nullable=False),
        sa.Column("match_strategy", sa.String(length=128), nullable=True),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column("matched_product_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("extra", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["dim_category.category_id"],
            name=op.f("fk_dim_product_category_id_dim_category"),
        ),
        sa.PrimaryKeyConstraint("product_id", name=op.f("pk_dim_product")),
    )
    with op.batch_alter_table("dim_product", schema=None) as batch_op:
        batch_op.create_index("ix_dim_product_active_seen", ["is_active", "last_seen_at"], unique=False)
        batch_op.create_index("ix_dim_product_brand", ["brand"], unique=False)
        batch_op.create_index("ix_dim_product_category", ["category_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_dim_product_fingerprint"), ["fingerprint"], unique=False)
        batch_op.create_index("ix_dim_product_name_search", ["canonical_name"], unique=False)
        batch_op.create_index("ix_dim_product_source_ext", ["source_code", "source_product_id"], unique=False)

    op.create_table(
        "dq_rule_result",
        sa.Column("result_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("rule_code", sa.String(length=128), nullable=False),
        sa.Column("rule_name", sa.String(length=512), nullable=True),
        sa.Column("dimension", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=128), nullable=False),
        sa.Column("table_name", sa.String(length=128), nullable=True),
        sa.Column("observed_value", sa.Float(), nullable=True),
        sa.Column("expected_value", sa.Float(), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("records_checked", sa.Integer(), nullable=False),
        sa.Column("records_failed", sa.Integer(), nullable=False),
        sa.Column("pass_rate_pct", sa.Float(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("evidence", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("evaluated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["etl_run.run_id"], name=op.f("fk_dq_rule_result_run_id_etl_run"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("result_id", name=op.f("pk_dq_rule_result")),
    )
    with op.batch_alter_table("dq_rule_result", schema=None) as batch_op:
        batch_op.create_index("ix_dq_rule_result_dimension", ["dimension"], unique=False)
        batch_op.create_index("ix_dq_rule_result_run", ["run_id"], unique=False)
        batch_op.create_index("ix_dq_rule_result_status", ["status"], unique=False)

    op.create_table(
        "app_job_event",
        sa.Column("event_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=128), nullable=False),
        sa.Column("stage", sa.String(length=128), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("progress_pct", sa.Integer(), nullable=True),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"], ["app_job.job_id"], name=op.f("fk_app_job_event_job_id_app_job"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_app_job_event")),
    )
    with op.batch_alter_table("app_job_event", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_app_job_event_created_at"), ["created_at"], unique=False)
        batch_op.create_index("ix_app_job_event_job", ["job_id", "event_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_app_job_event_job_id"), ["job_id"], unique=False)

    op.create_table(
        "app_notification",
        sa.Column("notification_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("alert_id", sa.Integer(), nullable=True),
        sa.Column("level", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.String(length=128), nullable=True),
        sa.Column("entity_id", sa.String(length=128), nullable=True),
        sa.Column("action_url", sa.String(length=512), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["app_alert_rule.alert_id"],
            name=op.f("fk_app_notification_alert_id_app_alert_rule"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.user_id"],
            name=op.f("fk_app_notification_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("notification_id", name=op.f("pk_app_notification")),
    )
    with op.batch_alter_table("app_notification", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_app_notification_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_app_notification_user_id"), ["user_id"], unique=False)
        batch_op.create_index("ix_app_notification_user_read", ["user_id", "is_read"], unique=False)

    op.create_table(
        "app_webhook_delivery",
        sa.Column("delivery_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("webhook_id", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("status", sa.String(length=128), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_excerpt", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("next_retry_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["webhook_id"],
            ["app_webhook.webhook_id"],
            name=op.f("fk_app_webhook_delivery_webhook_id_app_webhook"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("delivery_id", name=op.f("pk_app_webhook_delivery")),
    )
    with op.batch_alter_table("app_webhook_delivery", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_app_webhook_delivery_created_at"), ["created_at"], unique=False)
        batch_op.create_index("ix_app_webhook_delivery_hook", ["webhook_id", "created_at"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_app_webhook_delivery_next_retry_at"), ["next_retry_at"], unique=False
        )
        batch_op.create_index("ix_app_webhook_delivery_status", ["status", "next_retry_at"], unique=False)

    op.create_table(
        "chg_price_change",
        sa.Column("change_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("source_code", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("date_id", sa.Integer(), nullable=False),
        sa.Column("previous_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("new_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("change_abs", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("change_pct", sa.Float(), nullable=True),
        sa.Column("direction", sa.String(length=128), nullable=False),
        sa.Column("currency", sa.String(length=128), nullable=False),
        sa.Column("magnitude_band", sa.String(length=128), nullable=True),
        sa.Column("is_significant", sa.Boolean(), nullable=False),
        sa.Column("previous_price_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("new_price_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("detected_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["date_id"], ["dim_date.date_id"], name=op.f("fk_chg_price_change_date_id_dim_date")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["dim_product.product_id"],
            name=op.f("fk_chg_price_change_product_id_dim_product"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["etl_run.run_id"], name=op.f("fk_chg_price_change_run_id_etl_run")
        ),
        sa.ForeignKeyConstraint(
            ["source_code"],
            ["dim_source.source_code"],
            name=op.f("fk_chg_price_change_source_code_dim_source"),
        ),
        sa.PrimaryKeyConstraint("change_id", name=op.f("pk_chg_price_change")),
        sa.UniqueConstraint("product_id", "run_id", name="uq_chg_price_product_run"),
    )
    with op.batch_alter_table("chg_price_change", schema=None) as batch_op:
        batch_op.create_index("ix_chg_price_date_dir", ["date_id", "direction"], unique=False)
        batch_op.create_index("ix_chg_price_pct", ["change_pct"], unique=False)
        batch_op.create_index("ix_chg_price_significant", ["is_significant"], unique=False)

    op.create_table(
        "chg_product_event",
        sa.Column("event_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("source_code", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("date_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=128), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("old_category_id", sa.Integer(), nullable=True),
        sa.Column("new_category_id", sa.Integer(), nullable=True),
        sa.Column("days_missing", sa.Integer(), nullable=True),
        sa.Column("detected_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(none_as_null=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["date_id"], ["dim_date.date_id"], name=op.f("fk_chg_product_event_date_id_dim_date")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["dim_product.product_id"],
            name=op.f("fk_chg_product_event_product_id_dim_product"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["etl_run.run_id"], name=op.f("fk_chg_product_event_run_id_etl_run")
        ),
        sa.ForeignKeyConstraint(
            ["source_code"],
            ["dim_source.source_code"],
            name=op.f("fk_chg_product_event_source_code_dim_source"),
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_chg_product_event")),
    )
    with op.batch_alter_table("chg_product_event", schema=None) as batch_op:
        batch_op.create_index("ix_chg_event_product", ["product_id"], unique=False)
        batch_op.create_index("ix_chg_event_run", ["run_id"], unique=False)
        batch_op.create_index("ix_chg_event_type_date", ["event_type", "date_id"], unique=False)

    op.create_table(
        "fact_catalog_snapshot",
        sa.Column("match_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("catalog_sku", sa.String(length=128), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("source_code", sa.String(length=128), nullable=True),
        sa.Column("date_id", sa.Integer(), nullable=True),
        sa.Column("match_status", sa.String(length=128), nullable=False),
        sa.Column("match_strategy", sa.String(length=128), nullable=True),
        sa.Column("similarity_score", sa.Float(), nullable=True),
        sa.Column("scraped_name", sa.Text(), nullable=True),
        sa.Column("catalog_name", sa.Text(), nullable=True),
        sa.Column("scraped_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("catalog_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("price_gap_abs", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("price_gap_pct", sa.Float(), nullable=True),
        sa.Column("category_match", sa.Boolean(), nullable=True),
        sa.Column("brand_match", sa.Boolean(), nullable=True),
        sa.Column("is_price_mismatch", sa.Boolean(), nullable=False),
        sa.Column("matched_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(none_as_null=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["catalog_sku"],
            ["catalog_product.sku"],
            name=op.f("fk_fact_catalog_snapshot_catalog_sku_catalog_product"),
        ),
        sa.ForeignKeyConstraint(
            ["date_id"], ["dim_date.date_id"], name=op.f("fk_fact_catalog_snapshot_date_id_dim_date")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["dim_product.product_id"],
            name=op.f("fk_fact_catalog_snapshot_product_id_dim_product"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["etl_run.run_id"], name=op.f("fk_fact_catalog_snapshot_run_id_etl_run")
        ),
        sa.ForeignKeyConstraint(
            ["source_code"],
            ["dim_source.source_code"],
            name=op.f("fk_fact_catalog_snapshot_source_code_dim_source"),
        ),
        sa.PrimaryKeyConstraint("match_id", name=op.f("pk_fact_catalog_snapshot")),
        sa.UniqueConstraint("run_id", "catalog_sku", name="uq_fact_catalog_run_sku"),
    )
    with op.batch_alter_table("fact_catalog_snapshot", schema=None) as batch_op:
        batch_op.create_index("ix_fact_catalog_price_gap", ["price_gap_pct"], unique=False)
        batch_op.create_index("ix_fact_catalog_similarity", ["similarity_score"], unique=False)
        batch_op.create_index("ix_fact_catalog_status", ["match_status"], unique=False)

    op.create_table(
        "fact_price_snapshot",
        sa.Column("snapshot_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("source_code", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("date_id", sa.Integer(), nullable=False),
        sa.Column("captured_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("list_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("currency", sa.String(length=128), nullable=False),
        sa.Column("fx_rate_to_usd", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("price_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("discount_pct", sa.Float(), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("rating_count", sa.Integer(), nullable=True),
        sa.Column("availability", sa.String(length=128), nullable=True),
        sa.Column("in_stock", sa.Boolean(), nullable=True),
        sa.Column("price_change_abs", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("price_change_pct", sa.Float(), nullable=True),
        sa.Column("is_first_sighting", sa.Boolean(), nullable=False),
        sa.Column("product_url", sa.String(length=2048), nullable=True),
        sa.Column("raw_price_text", sa.String(length=128), nullable=True),
        sa.Column("quality_flags", sa.JSON(none_as_null=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["date_id"], ["dim_date.date_id"], name=op.f("fk_fact_price_snapshot_date_id_dim_date")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["dim_product.product_id"],
            name=op.f("fk_fact_price_snapshot_product_id_dim_product"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["etl_run.run_id"], name=op.f("fk_fact_price_snapshot_run_id_etl_run")
        ),
        sa.ForeignKeyConstraint(
            ["source_code"],
            ["dim_source.source_code"],
            name=op.f("fk_fact_price_snapshot_source_code_dim_source"),
        ),
        sa.PrimaryKeyConstraint("snapshot_id", name=op.f("pk_fact_price_snapshot")),
        sa.UniqueConstraint("product_id", "run_id", name="uq_fact_price_product_run"),
    )
    with op.batch_alter_table("fact_price_snapshot", schema=None) as batch_op:
        batch_op.create_index("ix_fact_price_change", ["price_change_pct"], unique=False)
        batch_op.create_index("ix_fact_price_date", ["date_id"], unique=False)
        batch_op.create_index("ix_fact_price_product_time", ["product_id", "captured_at"], unique=False)
        batch_op.create_index("ix_fact_price_run", ["run_id"], unique=False)
        batch_op.create_index("ix_fact_price_source_date", ["source_code", "date_id"], unique=False)

    # The views are not part of the ORM metadata, so they are applied here rather
    # than autogenerated.
    from app.etl.bootstrap import apply_views

    apply_views()


def downgrade() -> None:
    """Drop the analytical views, then every table.

    Views first: on PostgreSQL a view cannot be dropped while something still
    depends on it, and the views are built on the tables.
    """
    from app.etl.bootstrap import drop_views

    drop_views()
    with op.batch_alter_table("fact_price_snapshot", schema=None) as batch_op:
        batch_op.drop_index("ix_fact_price_source_date")
        batch_op.drop_index("ix_fact_price_run")
        batch_op.drop_index("ix_fact_price_product_time")
        batch_op.drop_index("ix_fact_price_date")
        batch_op.drop_index("ix_fact_price_change")

    op.drop_table("fact_price_snapshot")
    with op.batch_alter_table("fact_catalog_snapshot", schema=None) as batch_op:
        batch_op.drop_index("ix_fact_catalog_status")
        batch_op.drop_index("ix_fact_catalog_similarity")
        batch_op.drop_index("ix_fact_catalog_price_gap")

    op.drop_table("fact_catalog_snapshot")
    with op.batch_alter_table("chg_product_event", schema=None) as batch_op:
        batch_op.drop_index("ix_chg_event_type_date")
        batch_op.drop_index("ix_chg_event_run")
        batch_op.drop_index("ix_chg_event_product")

    op.drop_table("chg_product_event")
    with op.batch_alter_table("chg_price_change", schema=None) as batch_op:
        batch_op.drop_index("ix_chg_price_significant")
        batch_op.drop_index("ix_chg_price_pct")
        batch_op.drop_index("ix_chg_price_date_dir")

    op.drop_table("chg_price_change")
    with op.batch_alter_table("app_webhook_delivery", schema=None) as batch_op:
        batch_op.drop_index("ix_app_webhook_delivery_status")
        batch_op.drop_index(batch_op.f("ix_app_webhook_delivery_next_retry_at"))
        batch_op.drop_index("ix_app_webhook_delivery_hook")
        batch_op.drop_index(batch_op.f("ix_app_webhook_delivery_created_at"))

    op.drop_table("app_webhook_delivery")
    with op.batch_alter_table("app_notification", schema=None) as batch_op:
        batch_op.drop_index("ix_app_notification_user_read")
        batch_op.drop_index(batch_op.f("ix_app_notification_user_id"))
        batch_op.drop_index(batch_op.f("ix_app_notification_created_at"))

    op.drop_table("app_notification")
    with op.batch_alter_table("app_job_event", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_app_job_event_job_id"))
        batch_op.drop_index("ix_app_job_event_job")
        batch_op.drop_index(batch_op.f("ix_app_job_event_created_at"))

    op.drop_table("app_job_event")
    with op.batch_alter_table("dq_rule_result", schema=None) as batch_op:
        batch_op.drop_index("ix_dq_rule_result_status")
        batch_op.drop_index("ix_dq_rule_result_run")
        batch_op.drop_index("ix_dq_rule_result_dimension")

    op.drop_table("dq_rule_result")
    with op.batch_alter_table("dim_product", schema=None) as batch_op:
        batch_op.drop_index("ix_dim_product_source_ext")
        batch_op.drop_index("ix_dim_product_name_search")
        batch_op.drop_index(batch_op.f("ix_dim_product_fingerprint"))
        batch_op.drop_index("ix_dim_product_category")
        batch_op.drop_index("ix_dim_product_brand")
        batch_op.drop_index("ix_dim_product_active_seen")

    op.drop_table("dim_product")
    with op.batch_alter_table("app_webhook", schema=None) as batch_op:
        batch_op.drop_index("ix_app_webhook_user_active")
        batch_op.drop_index("ix_app_webhook_target")

    op.drop_table("app_webhook")
    with op.batch_alter_table("app_session", schema=None) as batch_op:
        batch_op.drop_index("ix_app_session_user_active")
        batch_op.drop_index("ix_app_session_expiry")
        batch_op.drop_index(batch_op.f("ix_app_session_expires_at"))
        batch_op.drop_index(batch_op.f("ix_app_session_created_at"))

    op.drop_table("app_session")
    with op.batch_alter_table("app_saved_view", schema=None) as batch_op:
        batch_op.drop_index("ix_app_saved_view_entity")

    op.drop_table("app_saved_view")
    with op.batch_alter_table("app_job", schema=None) as batch_op:
        batch_op.drop_index("ix_app_job_type_requested")
        batch_op.drop_index("ix_app_job_status_queued")
        batch_op.drop_index(batch_op.f("ix_app_job_status"))
        batch_op.drop_index(batch_op.f("ix_app_job_requested_by"))
        batch_op.drop_index(batch_op.f("ix_app_job_queued_at"))
        batch_op.drop_index(batch_op.f("ix_app_job_lease_owner"))
        batch_op.drop_index(batch_op.f("ix_app_job_job_type"))
        batch_op.drop_index(batch_op.f("ix_app_job_finished_at"))

    op.drop_table("app_job")
    with op.batch_alter_table("app_audit_log", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_app_audit_log_user_id"))
        batch_op.drop_index(batch_op.f("ix_app_audit_log_created_at"))
        batch_op.drop_index("ix_app_audit_action_time")

    op.drop_table("app_audit_log")
    with op.batch_alter_table("app_api_key", schema=None) as batch_op:
        batch_op.drop_index("ix_app_api_key_user")
        batch_op.drop_index(batch_op.f("ix_app_api_key_prefix"))

    op.drop_table("app_api_key")
    with op.batch_alter_table("app_alert_rule", schema=None) as batch_op:
        batch_op.drop_index("ix_app_alert_user_active")

    op.drop_table("app_alert_rule")
    with op.batch_alter_table("agg_category_daily", schema=None) as batch_op:
        batch_op.drop_index("ix_agg_cat_date")

    op.drop_table("agg_category_daily")
    with op.batch_alter_table("sync_state", schema=None) as batch_op:
        batch_op.drop_index("ix_sync_state_status")

    op.drop_table("sync_state")
    with op.batch_alter_table("stg_raw_observation", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_stg_raw_observation_source_product_id"))
        batch_op.drop_index(batch_op.f("ix_stg_raw_observation_source_code"))
        batch_op.drop_index("ix_stg_raw_observation_run_valid")
        batch_op.drop_index(batch_op.f("ix_stg_raw_observation_run_id"))
        batch_op.drop_index(batch_op.f("ix_stg_raw_observation_payload_hash"))
        batch_op.drop_index("ix_stg_raw_observation_landed")

    op.drop_table("stg_raw_observation")
    with op.batch_alter_table("ingestion_http_log", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ingestion_http_log_source_code"))
        batch_op.drop_index(batch_op.f("ix_ingestion_http_log_run_id"))
        batch_op.drop_index("ix_ingestion_http_log_run_host")
        batch_op.drop_index(batch_op.f("ix_ingestion_http_log_requested_at"))

    op.drop_table("ingestion_http_log")
    with op.batch_alter_table("etl_run", schema=None) as batch_op:
        batch_op.drop_index("ix_etl_run_trigger")
        batch_op.drop_index("ix_etl_run_target")
        batch_op.drop_index("ix_etl_run_status_started")

    op.drop_table("etl_run")
    with op.batch_alter_table("dim_source", schema=None) as batch_op:
        batch_op.drop_index("ix_dim_source_kind")
        batch_op.drop_index("ix_dim_source_enabled")

    op.drop_table("dim_source")
    with op.batch_alter_table("dim_date", schema=None) as batch_op:
        batch_op.drop_index("ix_dim_date_year_month")

    op.drop_table("dim_date")
    op.drop_table("dim_currency")
    with op.batch_alter_table("dim_category", schema=None) as batch_op:
        batch_op.drop_index("ix_dim_category_parent")
        batch_op.drop_index("ix_dim_category_name")

    op.drop_table("dim_category")
    with op.batch_alter_table("catalog_product", schema=None) as batch_op:
        batch_op.drop_index("ix_catalog_product_status")
        batch_op.drop_index("ix_catalog_product_category")
        batch_op.drop_index("ix_catalog_product_brand")

    op.drop_table("catalog_product")
    with op.batch_alter_table("app_user", schema=None) as batch_op:
        batch_op.drop_index("ix_app_user_role")
        batch_op.drop_index(batch_op.f("ix_app_user_email"))
        batch_op.drop_index("ix_app_user_active")

    op.drop_table("app_user")
    op.drop_table("app_setting")
    # ### end Alembic commands ###
