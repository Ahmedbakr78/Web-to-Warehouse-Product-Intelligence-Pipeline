"""Structured read-only view-builder API powering the dashboard Builder screen.

Unlike the free-form query lab (``/queries/execute``), this endpoint never
accepts raw SQL: the client picks a whitelisted entity, columns, operators
and aggregate functions, and the server assembles a parameterised SELECT.
Injection is structurally impossible because every identifier comes from
the ``ENTITIES`` whitelist and every value arrives as a bind parameter.
"""

from __future__ import annotations

import re
import time
from typing import Any, Literal

import sqlalchemy as sa
from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.api.deps import DbSession, QueryUser
from app.core.errors import ValidationError
from app.core.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/builder", tags=["builder"])

# --------------------------------------------------------------------------------------
# Entity catalogue: every identifier below is the ONLY thing that can reach the SQL text
# --------------------------------------------------------------------------------------
T = "text"
N = "number"
B = "boolean"
D = "datetime"

ENTITIES: dict[str, dict[str, Any]] = {
    "products": {
        "view": "vw_product_current",
        "label": "Current products",
        "columns": {
            "product_id": (N, False),
            "canonical_name": (T, True),
            "brand": (T, True),
            "category_name": (T, True),
            "category_path": (T, True),
            "availability": (T, True),
            "is_active": (B, False),
            "first_seen_at": (D, False),
            "last_seen_at": (D, False),
            "observation_count": (N, False),
            "match_strategy": (T, False),
            "match_score": (N, False),
            "captured_at": (D, False),
            "price": (N, True),
            "list_price": (N, False),
            "currency": (T, True),
            "price_usd": (N, True),
            "discount_pct": (N, False),
            "rating": (N, True),
            "rating_count": (N, False),
            "in_stock": (B, True),
            "price_change_abs": (N, False),
            "price_change_pct": (N, True),
            "source_code": (T, True),
        },
        "default_sort": ("captured_at", "desc"),
    },
    "price_changes": {
        "view": "vw_price_changes",
        "label": "Price changes",
        "columns": {
            "change_id": (N, False),
            "product_id": (N, False),
            "canonical_name": (T, True),
            "brand": (T, True),
            "category_name": (T, True),
            "source_code": (T, True),
            "full_date": (D, True),
            "previous_price_usd": (N, False),
            "new_price_usd": (N, False),
            "change_abs": (N, False),
            "change_pct": (N, True),
            "direction": (T, True),
            "magnitude_band": (T, True),
            "is_significant": (B, True),
            "currency": (T, True),
            "detected_at": (D, False),
        },
        "default_sort": ("detected_at", "desc"),
    },
    "new_products": {
        "view": "vw_new_products",
        "label": "New products",
        "columns": {
            "product_id": (N, False),
            "canonical_name": (T, True),
            "brand": (T, True),
            "category_name": (T, True),
            "source_code": (T, True),
            "price_usd": (N, True),
            "first_seen_price_usd": (N, False),
            "rating": (N, True),
            "availability": (T, True),
            "first_seen_at": (D, True),
        },
        "default_sort": ("first_seen_at", "desc"),
    },
    "removed_products": {
        "view": "vw_removed_products",
        "label": "Removed products",
        "columns": {
            "product_id": (N, False),
            "canonical_name": (T, True),
            "brand": (T, True),
            "category_name": (T, True),
            "source_code": (T, True),
            "days_missing": (N, True),
            "removed_date": (D, True),
            "last_known_price_usd": (N, True),
            "last_known_rating": (N, False),
            "detected_at": (D, False),
        },
        "default_sort": ("removed_date", "desc"),
    },
    "category_index": {
        "view": "vw_category_price_index",
        "label": "Category price index",
        "columns": {
            "date_id": (N, False),
            "full_date": (D, True),
            "category_name": (T, True),
            "observation_count": (N, True),
            "avg_price_usd": (N, True),
            "min_price_usd": (N, False),
            "max_price_usd": (N, False),
            "avg_rating": (N, True),
            "price_stddev": (N, False),
            "distinct_products": (N, True),
        },
        "default_sort": ("full_date", "desc"),
    },
    "brand_summary": {
        "view": "vw_brand_summary",
        "label": "Brand summary",
        "columns": {
            "brand": (T, True),
            "category_name": (T, True),
            "product_count": (N, True),
            "avg_price_usd": (N, True),
            "min_price_usd": (N, False),
            "max_price_usd": (N, False),
            "avg_rating": (N, True),
            "in_stock_observations": (N, False),
            "last_seen_at": (D, False),
        },
        "default_sort": ("product_count", "desc"),
    },
    "source_coverage": {
        "view": "vw_source_coverage",
        "label": "Source coverage",
        "columns": {
            "source_code": (T, True),
            "source_name": (T, True),
            "kind": (T, True),
            "enabled": (B, True),
            "products_seen": (N, True),
            "observations": (N, True),
            "avg_price_usd": (N, True),
            "avg_rating": (N, False),
            "last_observation_at": (D, False),
            "success_rate_pct": (N, True),
            "avg_duration_seconds": (N, True),
        },
        "default_sort": ("observations", "desc"),
    },
    "top_movers": {
        "view": "vw_top_movers",
        "label": "Top movers",
        "columns": {
            "product_id": (N, False),
            "canonical_name": (T, True),
            "category_name": (T, True),
            "source_code": (T, True),
            "full_date": (D, True),
            "previous_price": (N, False),
            "new_price": (N, False),
            "change_abs": (N, True),
            "change_pct": (N, True),
            "direction": (T, True),
            "magnitude_band": (T, True),
            "is_significant": (B, True),
        },
        "default_sort": ("change_abs", "desc"),
    },
    "availability": {
        "view": "vw_availability_summary",
        "label": "Availability summary",
        "columns": {
            "category_name": (T, True),
            "observations": (N, True),
            "in_stock_count": (N, True),
            "in_stock_pct": (N, True),
            "out_of_stock_count": (N, False),
        },
        "default_sort": ("observations", "desc"),
    },
    "quality_latest": {
        "view": "vw_quality_latest",
        "label": "Latest data-quality report",
        "columns": {
            "run_id": (T, False),
            "run_status": (T, True),
            "target_database": (T, True),
            "started_at": (D, False),
            "dq_score": (N, True),
            "rules_passed": (N, True),
            "rules_warned": (N, True),
            "rules_failed": (N, True),
            "rules_total": (N, False),
        },
        "default_sort": ("started_at", "desc"),
    },
    "catalog_reconciliation": {
        "view": "vw_catalog_reconciliation",
        "label": "Catalog reconciliation",
        "columns": {
            "match_id": (N, False),
            "run_id": (T, False),
            "catalog_sku": (T, True),
            "catalog_name": (T, True),
            "catalog_brand": (T, True),
            "catalog_category": (T, True),
            "catalog_price": (N, True),
            "supplier": (T, True),
            "scraped_name": (T, True),
            "scraped_brand": (T, True),
            "scraped_category": (T, True),
            "scraped_price_usd": (N, True),
            "price_gap_abs": (N, True),
            "price_gap_pct": (N, True),
            "match_status": (T, True),
            "match_strategy": (T, True),
            "similarity_score": (N, True),
            "category_match": (B, True),
            "brand_match": (B, True),
            "is_price_mismatch": (B, True),
            "matched_at": (D, False),
        },
        "default_sort": ("similarity_score", "desc"),
    },
    "pipeline_runs": {
        "view": "etl_run",
        "label": "Pipeline runs",
        "columns": {
            "run_id": (T, False),
            "status": (T, True),
            "trigger": (T, True),
            "target_database": (T, True),
            "started_at": (D, True),
            "finished_at": (D, False),
            "duration_ms": (N, True),
            "records_extracted": (N, True),
            "records_valid": (N, True),
            "records_rejected": (N, True),
            "records_inserted": (N, True),
            "duplicates_merged": (N, True),
            "new_products": (N, True),
            "price_changes": (N, True),
            "removed_products": (N, True),
            "catalog_matched": (N, True),
            "dq_score": (N, True),
            "dq_failed": (N, True),
        },
        "default_sort": ("started_at", "desc"),
    },
    "alert_rules": {
        "view": "app_alert_rule",
        "label": "Alert rules",
        "columns": {
            "alert_id": (N, False),
            "name": (T, True),
            "metric": (T, True),
            "operator": (T, True),
            "threshold": (N, True),
            "category": (T, True),
            "source_code": (T, True),
            "is_active": (B, True),
            "channel": (T, True),
            "trigger_count": (N, True),
            "last_triggered_at": (D, True),
        },
        "default_sort": ("trigger_count", "desc"),
    },
}

OPERATORS: dict[str, str] = {
    "eq": "=",
    "ne": "<>",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "contains": "LIKE",
    "not_contains": "NOT LIKE",
    "starts_with": "LIKE",
    "ends_with": "LIKE",
    "in": "IN",
    "not_in": "NOT IN",
    "between": "BETWEEN",
    "empty": "IS NULL",
    "not_empty": "IS NOT NULL",
}

AGGREGATES = ("count", "count_distinct", "sum", "avg", "min", "max")

#: Aggregate aliases are interpolated into the SQL text (bind parameters cannot
#: stand in for identifiers), so they must match a strict identifier shape.
ALIAS_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


# --------------------------------------------------------------------------------------
# Request models
# --------------------------------------------------------------------------------------
class BuilderFilter(BaseModel):
    column: str = Field(min_length=1, max_length=64)
    operator: str = Field(min_length=2, max_length=16)
    value: Any = None
    value2: Any = None

    @field_validator("operator")
    @classmethod
    def _known_operator(cls, value: str) -> str:
        if value not in OPERATORS:
            raise ValueError(f"unknown operator '{value}'")
        return value


class BuilderAggregate(BaseModel):
    function: str
    column: str | None = None
    alias: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("function")
    @classmethod
    def _known_function(cls, value: str) -> str:
        if value not in AGGREGATES:
            raise ValueError(f"unknown aggregate '{value}'")
        return value

    @field_validator("alias")
    @classmethod
    def _safe_alias(cls, value: str | None) -> str | None:
        if value is not None and not ALIAS_RE.match(value):
            raise ValueError(
                "alias must start with a letter and contain only letters, digits and underscores"
            )
        return value


class BuilderSort(BaseModel):
    column: str
    direction: str = "desc"

    @field_validator("direction")
    @classmethod
    def _known_direction(cls, value: str) -> str:
        if value not in ("asc", "desc"):
            raise ValueError(f"unknown direction '{value}'")
        return value


class BuilderQuery(BaseModel):
    entity: str = Field(min_length=1, max_length=64)
    columns: list[str] = Field(default_factory=list, max_length=32)
    filters: list[BuilderFilter] = Field(default_factory=list, max_length=16)
    #: How the WHERE filters combine. HAVING filters always combine with AND.
    filter_logic: Literal["and", "or"] = "and"
    group_by: list[str] = Field(default_factory=list, max_length=8)
    aggregates: list[BuilderAggregate] = Field(default_factory=list, max_length=8)
    #: Post-aggregation filters over grouping columns and aggregate aliases.
    having: list[BuilderFilter] = Field(default_factory=list, max_length=8)
    sort: list[BuilderSort] = Field(default_factory=list, max_length=4)
    limit: int = Field(default=25, ge=1, le=1000)
    offset: int = Field(default=0, ge=0, le=100000)


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def _entity(name: str) -> dict[str, Any]:
    if name not in ENTITIES:
        raise ValidationError(
            f"unknown entity '{name}'",
            details={"available": sorted(ENTITIES)},
        )
    return ENTITIES[name]


def _check_column(entity: dict[str, Any], column: str, *, what: str, groupable: bool = False) -> None:
    if column not in entity["columns"]:
        raise ValidationError(
            f"unknown {what} column '{column}'",
            details={"available": sorted(entity["columns"])},
        )
    if groupable and not entity["columns"][column][1]:
        groupable_names = sorted(name for name, (_kind, flag) in entity["columns"].items() if flag)
        raise ValidationError(
            f"column '{column}' is not groupable",
            details={"groupable": groupable_names},
        )


def _like_pattern(operator: str, value: Any) -> str:
    text = str(value)
    if operator == "contains":
        return f"%{text}%"
    if operator == "starts_with":
        return f"{text}%"
    return f"%{text}"


def _filter_clause(flt: BuilderFilter, bind: Any) -> str:
    """Render one filter to SQL. The column must already be allow-listed."""
    operator = flt.operator
    if operator in ("empty", "not_empty"):
        return f"{flt.column} {OPERATORS[operator]}"
    if flt.value is None:
        raise ValidationError(f"filter on '{flt.column}' requires a value")
    if operator in ("in", "not_in"):
        if not isinstance(flt.value, list) or not flt.value:
            raise ValidationError(f"operator '{operator}' requires a non-empty list value")
        return f"{flt.column} {OPERATORS[operator]} ({', '.join(bind(v) for v in flt.value)})"
    if operator == "between":
        if flt.value2 is None:
            raise ValidationError("operator 'between' requires value and value2")
        return f"{flt.column} BETWEEN {bind(flt.value)} AND {bind(flt.value2)}"
    if operator in ("contains", "not_contains", "starts_with", "ends_with"):
        return f"{flt.column} {OPERATORS[operator]} {bind(_like_pattern(operator, flt.value))}"
    return f"{flt.column} {OPERATORS[operator]} {bind(flt.value)}"


def _build_sql(query: BuilderQuery) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Assemble (sql, bind params, projection info) for a whitelisted SELECT."""
    entity = _entity(query.entity)
    columns = entity["columns"]
    params: dict[str, Any] = {}
    counter = 0

    def bind(value: Any) -> str:
        nonlocal counter
        counter += 1
        key = f"p{counter}"
        params[key] = value
        return f":{key}"

    if query.group_by or query.aggregates:
        selected: list[str] = []
        for name in query.group_by:
            _check_column(entity, name, what="group_by", groupable=True)
            selected.append(name)
        aliases: list[str] = []
        for aggregate in query.aggregates:
            if aggregate.column:
                _check_column(entity, aggregate.column, what="aggregate")
                if aggregate.function == "count_distinct":
                    expression = f"COUNT(DISTINCT {aggregate.column})"
                else:
                    expression = f"{aggregate.function.upper()}({aggregate.column})"
            else:
                if aggregate.function != "count":
                    raise ValidationError(f"aggregate '{aggregate.function}' requires a column")
                expression = "COUNT(*)"
            alias = aggregate.alias or f"{aggregate.function}_{aggregate.column or 'all'}"
            aliases.append(alias)
            selected.append(f"{expression} AS {alias}")
        if not selected:
            raise ValidationError("group_by or aggregates requires at least one grouping column")
        projection = ", ".join(selected)
        group_clause = f" GROUP BY {', '.join(query.group_by)}" if query.group_by else ""
        having_targets = set(query.group_by) | set(aliases)
        for flt in query.having:
            if flt.column not in having_targets:
                raise ValidationError(
                    f"unknown having column '{flt.column}'",
                    details={"available": sorted(having_targets)},
                )
        having_parts = [_filter_clause(flt, bind) for flt in query.having]
        having_clause = f" HAVING {' AND '.join(having_parts)}" if having_parts else ""
    else:
        if query.having:
            raise ValidationError("having requires group_by or aggregates")
        names = query.columns or [name for name, (_type, _flag) in columns.items()][:24]
        for name in names:
            _check_column(entity, name, what="select")
        projection = ", ".join(names)
        group_clause = ""
        having_clause = ""

    where_parts = []
    for flt in query.filters:
        _check_column(entity, flt.column, what="filter")
        where_parts.append(_filter_clause(flt, bind))
    joiner = " OR " if query.filter_logic == "or" else " AND "
    where_clause = f" WHERE {joiner.join(where_parts)}" if where_parts else ""

    # Sort columns are validated by _validate_sort (they may be aggregate aliases).
    order_parts = [f"{rule.column} {rule.direction.upper()}" for rule in query.sort]
    if not order_parts:
        if query.group_by or query.aggregates:
            # Grouped queries previously emitted no ORDER BY at all, which made
            # OFFSET paging non-deterministic. Default to the first grouping
            // aggregate so pages are stable.
            fallback = (query.group_by or [aliases[0] if (aliases := [a.alias or f"{a.function}_{a.column or 'all'}" for a in query.aggregates]) else None])
            if fallback[0]:
                order_parts = [f"{fallback[0]} DESC"]
        else:
            default_column, default_direction = entity["default_sort"]
            order_parts = [f"{default_column} {default_direction.upper()}"]
    order_clause = f" ORDER BY {', '.join(order_parts)}" if order_parts else ""

    sql = f"SELECT {projection} FROM {entity['view']}{where_clause}{group_clause}{having_clause}{order_clause}"
    return sql, params, {"projection": projection}


def _validate_sort(query: BuilderQuery, entity: dict[str, Any]) -> None:
    """Sort columns must be entity columns - or grouping columns/aggregate aliases when grouped."""
    aliases = {
        aggregate.alias or f"{aggregate.function}_{aggregate.column or 'all'}"
        for aggregate in query.aggregates
    }
    if query.group_by or query.aggregates:
        allowed = set(query.group_by) | aliases
        for rule in query.sort:
            if rule.column not in allowed:
                raise ValidationError(
                    f"unknown sort column '{rule.column}' for a grouped query",
                    details={"available": sorted(allowed)},
                )
        return
    for rule in query.sort:
        if rule.column not in entity["columns"]:
            raise ValidationError(
                f"unknown sort column '{rule.column}'",
                details={"available": sorted(entity["columns"])},
            )


# --------------------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------------------
@router.get("/schema", summary="Entities, columns, operators and aggregates for the builder")
def schema(_user: QueryUser) -> dict[str, Any]:
    entities = [
        {
            "entity": key,
            "label": spec["label"],
            "view": spec["view"],
            "default_sort": {"column": spec["default_sort"][0], "direction": spec["default_sort"][1]},
            "columns": [
                {"name": name, "type": kind, "groupable": groupable}
                for name, (kind, groupable) in spec["columns"].items()
            ],
        }
        for key, spec in ENTITIES.items()
    ]
    return {
        "entities": entities,
        "operators": [
            {
                "operator": key,
                "sql": value,
                "value_type": "list"
                if key in ("in", "not_in")
                else (
                    "range" if key == "between" else ("none" if key in ("empty", "not_empty") else "scalar")
                ),
            }
            for key, value in OPERATORS.items()
        ],
        "aggregates": list(AGGREGATES),
        "max_limit": 1000,
    }


@router.post("/query", summary="Run a structured read-only query (whitelisted identifiers only)")
def run_query(payload: BuilderQuery, session: DbSession, _user: QueryUser) -> dict[str, Any]:
    entity = _entity(payload.entity)
    _validate_sort(payload, entity)
    started = time.perf_counter()
    sql, params, _info = _build_sql(payload)
    result = session.execute(
        sa.text(f"SELECT * FROM ({sql}) AS built_query LIMIT :lim OFFSET :off"),
        {**params, "lim": payload.limit + 1, "off": payload.offset},
    )
    columns = list(result.keys())
    rows = result.fetchmany(payload.limit + 1)
    truncated = len(rows) > payload.limit
    rows = rows[: payload.limit]
    total = session.execute(sa.text(f"SELECT COUNT(*) FROM ({sql}) AS counted"), params).scalar() or 0
    duration = round((time.perf_counter() - started) * 1000, 2)
    log.info("builder query entity=%s rows=%d duration_ms=%s", payload.entity, len(rows), duration)
    return {
        "entity": payload.entity,
        "label": entity["label"],
        "columns": columns,
        "rows": [_jsonify_row(row) for row in rows],
        "row_count": len(rows),
        "total": int(total),
        "truncated": truncated,
        "group_by": payload.group_by,
        "aggregates": [agg.model_dump() for agg in payload.aggregates],
        "sql_preview": sql,
        "duration_ms": duration,
    }


def _jsonify_row(row: Any) -> list[Any]:
    import datetime as dt
    import decimal

    values: list[Any] = []
    for value in row:
        if isinstance(value, (dt.datetime, dt.date, dt.time)):
            values.append(value.isoformat())
        elif isinstance(value, decimal.Decimal):
            values.append(float(value))
        else:
            values.append(value)
    return values
