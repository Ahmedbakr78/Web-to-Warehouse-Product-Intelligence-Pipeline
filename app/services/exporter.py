"""Universal dataset export: one registry drives CSV and JSON downloads.

Every list surface in the dashboard can be handed to a user as a file. Rather than
writing one ad-hoc endpoint per screen, datasets are declared once here and served
in any format through ``GET /export/{dataset}.{fmt}``.

Design notes:
    * SQL is parameterised - filters are bound, never interpolated.
    * Identifiers are validated against a strict pattern before being used in SQL.
    * Row limits are enforced in the database (``LIMIT``) so exports cannot exhaust
      memory on large warehouses.
    * Timestamps and decimals are normalised so CSV and JSON agree cell by cell.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import PipelineError

MAX_ROWS = 50_000
DEFAULT_ROWS = 5_000
SAFE_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


class ExportError(PipelineError):
    """Raised for unknown datasets, bad formats or malformed filter values."""

    status_code = 400
    code = "export_error"


@dataclass(frozen=True)
class Dataset:
    """One exportable dataset: SQL plus the filters it understands."""

    key: str
    title: str
    description: str
    group: str
    sql: str
    default_order: str = ""
    filters: tuple[str, ...] = field(default=())
    columns: tuple[str, ...] = field(default=())

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "description": self.description,
            "group": self.group,
            "filters": list(self.filters),
            "columns": list(self.columns),
        }


DATASETS: dict[str, Dataset] = {
    dataset.key: dataset
    for dataset in (
        Dataset(
            key="products",
            title="Products (current state)",
            description="Latest state per canonical product with price, rating and movement.",
            group="Warehouse",
            sql="""
                SELECT product_id, canonical_name, brand, category_name, availability,
                       price, price_usd, currency, rating, price_change_pct,
                       last_seen_at, source_code, product_url
                FROM vw_product_current
                {where}
                ORDER BY product_id
                LIMIT :row_limit
            """,
            filters=("source_code", "category_name", "availability", "search"),
        ),
        Dataset(
            key="price_changes",
            title="Price change events",
            description="Every recorded price movement with absolute and percentage deltas.",
            group="Changes",
            sql="""
                SELECT change_id, product_id, canonical_name, brand, category_name,
                       source_code, previous_price, new_price, change_abs, change_pct,
                       direction, magnitude_band, is_significant, currency, detected_at
                FROM vw_price_changes
                {where}
                ORDER BY detected_at DESC, change_id DESC
                LIMIT :row_limit
            """,
            filters=("source_code", "direction"),
        ),
        Dataset(
            key="new_products",
            title="Newly discovered products",
            description="First sightings per product with the run that found them.",
            group="Changes",
            sql="""
                SELECT product_id, canonical_name, brand, category_name, source_code,
                       price_usd, currency, rating, availability, product_url,
                       first_seen_at, first_seen_date, detected_at
                FROM vw_new_products
                {where}
                ORDER BY first_seen_at DESC
                LIMIT :row_limit
            """,
            filters=("source_code",),
        ),
        Dataset(
            key="removed_products",
            title="Removed products",
            description="Products that disappeared from a source between runs.",
            group="Changes",
            sql="""
                SELECT product_id, canonical_name, brand, category_name, source_code,
                       old_value, days_missing, last_known_price_usd, last_known_rating,
                       detected_at, removed_date
                FROM vw_removed_products
                {where}
                ORDER BY detected_at DESC
                LIMIT :row_limit
            """,
            filters=("source_code",),
        ),
        Dataset(
            key="runs",
            title="Pipeline runs",
            description="Run history with record counts, DQ scores and orchestration lineage.",
            group="Operations",
            sql="""
                SELECT run_id, status, trigger, target_database, dag_id, task_id,
                       started_at, finished_at, duration_ms, records_extracted,
                       records_valid, records_rejected, duplicates_merged,
                       new_products, price_changes, removed_products, dq_score,
                       dq_passed, dq_failed, error_message
                FROM etl_run
                {where}
                ORDER BY started_at DESC
                LIMIT :row_limit
            """,
            filters=("status", "trigger", "database"),
        ),
        Dataset(
            key="quality",
            title="Data quality results",
            description="Per-run DQ rule outcomes including pass rates and messages.",
            group="Quality",
            sql="""
                SELECT run_id, rule_code, rule_name, dimension, severity, status,
                       table_name, observed_value, expected_value, threshold,
                       records_checked, records_failed, pass_rate_pct, message, evaluated_at
                FROM dq_rule_result
                {where}
                ORDER BY evaluated_at DESC, rule_code
                LIMIT :row_limit
            """,
            filters=("status", "severity", "dimension"),
        ),
        Dataset(
            key="catalog",
            title="Catalog reconciliation",
            description="Scraped products matched against the internal catalog with similarity.",
            group="Warehouse",
            sql="""
                SELECT match_id, run_id, catalog_sku, catalog_name, catalog_brand,
                       catalog_category, product_id, scraped_name, match_status,
                       match_strategy, similarity_score, category_match, brand_match,
                       catalog_price, scraped_price_usd, price_gap_abs, price_gap_pct,
                       is_price_mismatch, supplier, matched_at
                FROM vw_catalog_reconciliation
                {where}
                ORDER BY match_id DESC
                LIMIT :row_limit
            """,
            filters=("match_status",),
        ),
        Dataset(
            key="categories",
            title="Category tree",
            description="Hierarchical categories with product and price aggregates.",
            group="Warehouse",
            sql="""
                SELECT category_id, parent_id, name, slug, path, level,
                       product_count, active_products, avg_price_usd
                FROM vw_category_tree
                {where}
                ORDER BY path
                LIMIT :row_limit
            """,
            filters=(),
        ),
        Dataset(
            key="movers",
            title="Top price movers",
            description="Largest absolute and percentage price movements.",
            group="Changes",
            sql="""
                SELECT product_id, canonical_name, category_name, source_code,
                       full_date, previous_price, new_price, change_abs, change_pct,
                       direction, magnitude_band, is_significant
                FROM vw_top_movers
                {where}
                ORDER BY ABS(change_pct) DESC
                LIMIT :row_limit
            """,
            filters=("source_code", "direction"),
        ),
        Dataset(
            key="sources",
            title="Source coverage",
            description="Per-source product counts, coverage and last sync state.",
            group="Operations",
            sql="""
                SELECT source_code, source_name, kind, enabled, rate_limit_per_minute,
                       products_seen, observations, avg_price_usd, avg_rating,
                       success_rate_pct, avg_duration_seconds, last_observation_at
                FROM vw_source_coverage
                {where}
                ORDER BY source_code
                LIMIT :row_limit
            """,
            filters=("enabled",),
        ),
        Dataset(
            key="alerts",
            title="Alert rules",
            description="Configured alert rules with severity and trigger conditions.",
            group="Operations",
            sql="""
                SELECT alert_id, user_id, name, metric, operator, threshold,
                       category, source_code, channel, is_active,
                       trigger_count, last_triggered_at, created_at
                FROM app_alert_rule
                {where}
                ORDER BY created_at DESC
                LIMIT :row_limit
            """,
            filters=("is_active", "channel"),
        ),
        Dataset(
            key="audit",
            title="Audit log",
            description="Who changed what, with before/after values and IP address.",
            group="Security",
            sql="""
                SELECT audit_id, user_id, user_email, action, entity_type, entity_id,
                       status, ip_address, user_agent, duration_ms, details, created_at
                FROM app_audit_log
                {where}
                ORDER BY created_at DESC
                LIMIT :row_limit
            """,
            filters=("action", "user_email"),
        ),
        Dataset(
            key="http_audit",
            title="HTTP compliance log",
            description="Outbound requests with robots.txt decision, status and timing.",
            group="Security",
            sql="""
                SELECT log_id, run_id, source_code, host, method, url, status_code,
                       robots_allowed, from_cache, elapsed_ms, response_bytes, requested_at
                FROM vw_http_audit
                {where}
                ORDER BY requested_at DESC
                LIMIT :row_limit
            """,
            filters=("source_code", "robots_allowed"),
        ),
    )
}


def list_datasets() -> list[dict[str, Any]]:
    """Catalogue of exportable datasets for the UI."""
    return [dataset.as_dict() for dataset in DATASETS.values()]


def get_dataset(key: str) -> Dataset:
    dataset = DATASETS.get(key)
    if dataset is None:
        raise ExportError(f"unknown dataset '{key}'", details={"available": sorted(DATASETS)})
    return dataset


def _cell(value: Any) -> Any:
    """Normalise a DB value so CSV and JSON carry the same information."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dt.time):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def _build_where(dataset: Dataset, filters: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Translate query-string filters into a parameterised WHERE clause."""
    clauses: list[str] = []
    params: dict[str, Any] = {}

    column_for = {
        "database": "target_database",
        "trigger": "trigger",
        "is_active": "is_active",
        "enabled": "enabled",
        "robots_allowed": "robots_allowed",
    }

    for name, raw in filters.items():
        if raw is None or raw == "":
            continue
        if name not in dataset.filters:
            raise ExportError(
                f"filter '{name}' is not supported by dataset '{dataset.key}'",
                details={"supported": list(dataset.filters)},
            )
        column = column_for.get(name, name)
        if not SAFE_IDENTIFIER.match(column):
            raise ExportError(f"invalid filter column '{column}'")
        value: Any = raw
        if name in {"is_active", "enabled", "robots_allowed"}:
            if str(raw).lower() not in {"true", "false", "1", "0"}:
                raise ExportError(f"filter '{name}' must be a boolean")
            value = str(raw).lower() in {"true", "1"}
        if name == "search":
            # Free-text search across the dataset's obvious text columns
            search_cols = {
                "products": "canonical_name",
                "new_products": "canonical_name",
                "removed_products": "canonical_name",
                "price_changes": "canonical_name",
                "movers": "canonical_name",
            }.get(dataset.key, "canonical_name")
            clauses.append(f"{search_cols} ILIKE :search")
            params["search"] = f"%{raw}%"
            continue
        if name == "direction":
            direction = str(raw).lower()
            if direction not in {"up", "down"}:
                raise ExportError("filter 'direction' must be 'up' or 'down'")
            clauses.append("change_pct > 0" if direction == "up" else "change_pct < 0")
            continue
        clauses.append(f"{column} = :f_{name}")
        params[f"f_{name}"] = value

    return (" WHERE " + " AND ".join(clauses) if clauses else ""), params


def fetch_rows(
    session: Session,
    key: str,
    filters: dict[str, Any] | None = None,
    row_limit: int = DEFAULT_ROWS,
) -> tuple[Dataset, list[dict[str, Any]]]:
    """Run a dataset query and return the dataset plus materialised rows."""
    dataset = get_dataset(key)
    if not 1 <= row_limit <= MAX_ROWS:
        raise ExportError(f"row_limit must be between 1 and {MAX_ROWS}")

    where, params = _build_where(dataset, filters or {})
    params["row_limit"] = row_limit
    sql = dataset.sql.format(where=where)
    result = session.execute(text(sql), params)
    rows: list[dict[str, Any]] = [
        {key_: _cell(value) for key_, value in dict(row).items()} for row in result.mappings()
    ]
    return dataset, rows


def to_csv(rows: list[dict[str, Any]], columns: tuple[str, ...] | None = None) -> str:
    """Serialise rows to CSV with a header row (empty string when there is no data)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    if not rows:
        return ""
    header = list(columns) if columns else list(rows[0].keys())
    writer.writerow(header)
    for row in rows:
        writer.writerow(["" if row.get(col) is None else row.get(col) for col in header])
    return buffer.getvalue()


def to_json(rows: list[dict[str, Any]], dataset: Dataset, row_limit: int) -> str:
    """Serialise rows to a JSON envelope that documents the export itself."""
    payload = {
        "dataset": dataset.key,
        "title": dataset.title,
        "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "row_count": len(rows),
        "row_limit": row_limit,
        "columns": list(rows[0].keys()) if rows else list(dataset.columns),
        "rows": rows,
    }
    return json.dumps(payload, indent=2, default=str)


def filename_for(dataset: Dataset, fmt: str, stamp: str | None = None) -> str:
    """Deterministic download filename, e.g. ``products-2026-10-05.csv``."""
    suffix = stamp or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    return f"{dataset.key}-{suffix}.{fmt}"


__all__ = [
    "DATASETS",
    "DEFAULT_ROWS",
    "MAX_ROWS",
    "Dataset",
    "ExportError",
    "fetch_rows",
    "filename_for",
    "get_dataset",
    "list_datasets",
    "to_csv",
    "to_json",
]
