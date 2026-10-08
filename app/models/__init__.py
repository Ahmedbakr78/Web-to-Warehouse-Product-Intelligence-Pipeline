"""Model registry: import every mapped class so ``Base.metadata`` is complete."""

from __future__ import annotations

from app.models.app_users import (
    AppAlertRule,
    AppApiKey,
    AppAuditLog,
    AppJob,
    AppJobEvent,
    AppNotification,
    AppQueryHistory,
    AppSavedView,
    AppSession,
    AppSetting,
    AppUser,
    AppWebhook,
    AppWebhookDelivery,
)
from app.models.base import Base
from app.models.catalog import CatalogProduct
from app.models.dimensions import DimCategory, DimCurrency, DimDate, DimProduct, DimSource
from app.models.facts import (
    AggCategoryDaily,
    ChgPriceChange,
    ChgProductEvent,
    FactCatalogSnapshot,
    FactPriceSnapshot,
)
from app.models.operations import (
    DqRuleResult,
    EtlRun,
    IngestionHttpLog,
    StgRawObservation,
    SyncState,
)

# --------------------------------------------------------------------------------------
# Convenience name -> class map used by the CLI, DQ framework and API serializers.
# --------------------------------------------------------------------------------------
ALL_MODELS = (
    DimSource,
    DimCategory,
    DimProduct,
    DimDate,
    DimCurrency,
    FactPriceSnapshot,
    FactCatalogSnapshot,
    ChgPriceChange,
    ChgProductEvent,
    AggCategoryDaily,
    CatalogProduct,
    EtlRun,
    DqRuleResult,
    IngestionHttpLog,
    StgRawObservation,
    SyncState,
    AppUser,
    AppApiKey,
    AppSavedView,
    AppQueryHistory,
    AppAlertRule,
    AppNotification,
    AppAuditLog,
    AppSetting,
    AppJob,
    AppJobEvent,
    AppSession,
    AppJob,
    AppJobEvent,
    AppSession,
    AppWebhook,
    AppWebhookDelivery,
)

MODEL_BY_TABLE: dict[str, type[Base]] = {model.__tablename__: model for model in ALL_MODELS}

CORE_TABLES: tuple[str, ...] = (
    "dim_source",
    "dim_category",
    "dim_date",
    "dim_currency",
    "dim_product",
    "fact_price_snapshot",
    "fact_catalog_snapshot",
    "chg_price_change",
    "chg_product_event",
    "agg_category_daily",
    "catalog_product",
    "etl_run",
    "dq_rule_result",
    "ingestion_http_log",
    "stg_raw_observation",
    "sync_state",
    "app_user",
    "app_api_key",
    "app_saved_view",
    "app_query_history",
    "app_alert_rule",
    "app_notification",
    "app_audit_log",
    "app_setting",
    "app_webhook",
    "app_webhook_delivery",
    "app_job",
    "app_job_event",
    "app_session",
)

#: Logical groups drive the documentation ERD and the API surface.
TABLE_GROUPS: dict[str, tuple[str, ...]] = {
    "dimensions": ("dim_source", "dim_category", "dim_date", "dim_currency", "dim_product"),
    "facts": ("fact_price_snapshot", "fact_catalog_snapshot", "agg_category_daily"),
    "changes": ("chg_price_change", "chg_product_event"),
    "operations": ("etl_run", "dq_rule_result", "ingestion_http_log", "stg_raw_observation", "sync_state"),
    "catalog": ("catalog_product",),
    "application": (
        "app_user",
        "app_api_key",
        "app_saved_view",
        "app_query_history",
        "app_alert_rule",
        "app_notification",
        "app_audit_log",
        "app_setting",
    ),
    "integrations": ("app_webhook", "app_webhook_delivery"),
    "jobs": ("app_job", "app_job_event"),
    "sessions": ("app_session",),
}


def all_tables() -> list[str]:
    """Sorted list of every physical table name managed by the ORM."""
    return sorted(Base.metadata.tables)


def table_count() -> int:
    return len(Base.metadata.tables)


__all__ = [
    "Base",
    "ALL_MODELS",
    "MODEL_BY_TABLE",
    "CORE_TABLES",
    "TABLE_GROUPS",
    "DimSource",
    "DimCategory",
    "DimProduct",
    "DimDate",
    "DimCurrency",
    "FactPriceSnapshot",
    "FactCatalogSnapshot",
    "ChgPriceChange",
    "ChgProductEvent",
    "AggCategoryDaily",
    "CatalogProduct",
    "EtlRun",
    "DqRuleResult",
    "IngestionHttpLog",
    "StgRawObservation",
    "SyncState",
    "AppUser",
    "AppJob",
    "AppJobEvent",
    "AppSession",
    "AppWebhook",
    "AppWebhookDelivery",
    "AppApiKey",
    "AppSavedView",
    "AppAlertRule",
    "AppNotification",
    "AppAuditLog",
    "AppSetting",
    "all_tables",
    "table_count",
]
