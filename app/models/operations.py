"""Operational metadata: pipeline runs, data-quality results, HTTP audit, sync cursors."""

from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import UTCDateTime, Base, JSONType, MediumStr, ShortStr, UrlStr, utcnow


class EtlRun(Base):
    """One execution of the pipeline (Airflow task, CLI call, API trigger or cron)."""

    __tablename__ = "etl_run"

    run_id: Mapped[str] = mapped_column(ShortStr, primary_key=True)
    run_key: Mapped[str | None] = mapped_column(ShortStr)
    pipeline: Mapped[str] = mapped_column(ShortStr, nullable=False, default="product_intelligence")
    target_database: Mapped[str] = mapped_column(ShortStr, nullable=False, default="postgres")
    dag_id: Mapped[str | None] = mapped_column(ShortStr)
    task_id: Mapped[str | None] = mapped_column(ShortStr)
    status: Mapped[str] = mapped_column(ShortStr, nullable=False, default="pending")
    trigger: Mapped[str] = mapped_column(ShortStr, nullable=False, default="manual")
    started_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), default=utcnow, nullable=False
    )
    finished_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer)
    records_extracted: Mapped[int] = mapped_column(sa.Integer, default=0)
    records_valid: Mapped[int] = mapped_column(sa.Integer, default=0)
    records_rejected: Mapped[int] = mapped_column(sa.Integer, default=0)
    records_inserted: Mapped[int] = mapped_column(sa.Integer, default=0)
    records_updated: Mapped[int] = mapped_column(sa.Integer, default=0)
    duplicates_merged: Mapped[int] = mapped_column(sa.Integer, default=0)
    new_products: Mapped[int] = mapped_column(sa.Integer, default=0)
    price_changes: Mapped[int] = mapped_column(sa.Integer, default=0)
    removed_products: Mapped[int] = mapped_column(sa.Integer, default=0)
    catalog_matched: Mapped[int] = mapped_column(sa.Integer, default=0)
    dq_passed: Mapped[int] = mapped_column(sa.Integer, default=0)
    dq_failed: Mapped[int] = mapped_column(sa.Integer, default=0)
    dq_score: Mapped[float | None] = mapped_column(sa.Float)
    error_message: Mapped[str | None] = mapped_column(sa.Text)
    warnings: Mapped[list | None] = mapped_column(JSONType, default=list)
    params: Mapped[dict | None] = mapped_column(JSONType, default=dict)
    created_by: Mapped[str | None] = mapped_column(ShortStr)
    created_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), default=utcnow, nullable=False
    )

    __table_args__ = (
        sa.Index("ix_etl_run_status_started", "status", "started_at"),
        sa.Index("ix_etl_run_target", "target_database"),
        sa.Index("ix_etl_run_trigger", "trigger"),
    )


class DqRuleResult(Base):
    """Output of one data-quality rule evaluation inside a run."""

    __tablename__ = "dq_rule_result"

    result_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ShortStr, sa.ForeignKey("etl_run.run_id", ondelete="CASCADE"))
    rule_code: Mapped[str] = mapped_column(ShortStr, nullable=False)
    rule_name: Mapped[str | None] = mapped_column(MediumStr)
    dimension: Mapped[str] = mapped_column(ShortStr, nullable=False)  # completeness|validity|...
    severity: Mapped[str] = mapped_column(ShortStr, nullable=False, default="error")
    status: Mapped[str] = mapped_column(ShortStr, nullable=False, default="pass")
    table_name: Mapped[str | None] = mapped_column(ShortStr)
    observed_value: Mapped[float | None] = mapped_column(sa.Float)
    expected_value: Mapped[float | None] = mapped_column(sa.Float)
    threshold: Mapped[float | None] = mapped_column(sa.Float)
    records_checked: Mapped[int] = mapped_column(sa.Integer, default=0)
    records_failed: Mapped[int] = mapped_column(sa.Integer, default=0)
    pass_rate_pct: Mapped[float | None] = mapped_column(sa.Float)
    message: Mapped[str | None] = mapped_column(sa.Text)
    evidence: Mapped[dict | None] = mapped_column(JSONType, default=dict)
    evaluated_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), default=utcnow, nullable=False
    )

    __table_args__ = (
        sa.Index("ix_dq_rule_result_run", "run_id"),
        sa.Index("ix_dq_rule_result_status", "status"),
        sa.Index("ix_dq_rule_result_dimension", "dimension"),
    )


class IngestionHttpLog(Base):
    """Compliance audit trail: one row per outbound HTTP request."""

    __tablename__ = "ingestion_http_log"

    log_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(ShortStr, index=True)
    source_code: Mapped[str | None] = mapped_column(ShortStr, index=True)
    method: Mapped[str] = mapped_column(ShortStr, default="GET")
    url: Mapped[str] = mapped_column(UrlStr, nullable=False)
    host: Mapped[str | None] = mapped_column(ShortStr)
    status_code: Mapped[int | None] = mapped_column(sa.Integer)
    elapsed_ms: Mapped[float | None] = mapped_column(sa.Float)
    response_bytes: Mapped[int | None] = mapped_column(sa.Integer)
    robots_allowed: Mapped[bool | None] = mapped_column(sa.Boolean)
    robots_rule: Mapped[str | None] = mapped_column(ShortStr)
    from_cache: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    retry_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    error: Mapped[str | None] = mapped_column(sa.Text)
    requested_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), default=utcnow, nullable=False, index=True
    )

    __table_args__ = (
        sa.Index("ix_ingestion_http_log_run_host", "run_id", "host"),
    )


class StgRawObservation(Base):
    """Landing / staging zone: raw payloads exactly as received (before cleaning)."""

    __tablename__ = "stg_raw_observation"

    observation_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(ShortStr, index=True)
    source_code: Mapped[str] = mapped_column(ShortStr, nullable=False, index=True)
    source_product_id: Mapped[str | None] = mapped_column(ShortStr, index=True)
    entity_type: Mapped[str] = mapped_column(ShortStr, default="product")
    source_url: Mapped[str | None] = mapped_column(UrlStr)
    raw_name: Mapped[str | None] = mapped_column(sa.Text)
    raw_category: Mapped[str | None] = mapped_column(MediumStr)
    raw_price_text: Mapped[str | None] = mapped_column(ShortStr)
    raw_currency: Mapped[str | None] = mapped_column(ShortStr)
    raw_rating_text: Mapped[str | None] = mapped_column(ShortStr)
    raw_availability: Mapped[str | None] = mapped_column(ShortStr)
    raw_payload: Mapped[dict | None] = mapped_column(JSONType, default=dict)
    payload_hash: Mapped[str | None] = mapped_column(ShortStr, index=True)
    http_status: Mapped[int | None] = mapped_column(sa.Integer)
    is_valid: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    reject_reason: Mapped[str | None] = mapped_column(MediumStr)
    fetched_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), default=utcnow, nullable=False
    )
    landed_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), default=utcnow, nullable=False
    )

    __table_args__ = (
        sa.Index("ix_stg_raw_observation_run_valid", "run_id", "is_valid"),
        sa.Index("ix_stg_raw_observation_landed", "landed_at"),
    )


class SyncState(Base):
    """Incremental checkpoint per source so runs can resume / be incremental."""

    __tablename__ = "sync_state"

    source_code: Mapped[str] = mapped_column(ShortStr, primary_key=True)
    last_run_id: Mapped[str | None] = mapped_column(ShortStr)
    last_success_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    last_attempt_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    cursor_value: Mapped[str | None] = mapped_column(MediumStr)
    cursor_json: Mapped[dict | None] = mapped_column(JSONType, default=dict)
    total_extracted: Mapped[int] = mapped_column(sa.BigInteger, default=0)
    consecutive_failures: Mapped[int] = mapped_column(sa.Integer, default=0)
    status: Mapped[str] = mapped_column(ShortStr, default="idle")
    message: Mapped[str | None] = mapped_column(sa.Text)

    __table_args__ = (
        sa.Index("ix_sync_state_status", "status"),
    )


__all__ = [
    "EtlRun",
    "DqRuleResult",
    "IngestionHttpLog",
    "StgRawObservation",
    "SyncState",
]