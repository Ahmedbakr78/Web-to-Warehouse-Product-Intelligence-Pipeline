"""Remove warehouse rows that did not come from a genuine market source.

The pipeline classifies every source with a trust level (``real``, ``sandbox``,
``synthetic`` - see :mod:`app.ingestion.base`). Rows written by a source below
``real`` are, by definition, records nobody observed: a mock API's invented
catalogue, a scraping sandbox's fictional shop, or a locally generated row.

Such rows are still useful while experimenting, but a warehouse that claims to
be a market picture must not contain them. This module deletes them and reports
exactly what it removed, so the operation is auditable rather than silent.

Deletion order respects the foreign keys: staging and facts first, then the
products that no longer have any observation, then the runs that no longer
reference anything. The dimension row of every source is kept - it is the
record of *why* the data was removed - but the source is disabled so no future
automatic run picks it up.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.db import session_scope
from app.core.logging import get_logger
from app.ingestion.base import DATA_TRUST_REAL

log = get_logger(__name__)

#: Tables whose rows carry a ``source_code`` and are removed wholesale for an
#: untrusted source. Ordered so that children are deleted before parents.
_SOURCE_SCOPED_TABLES: tuple[str, ...] = (
    "stg_raw_observation",
    "ingestion_http_log",
    "sync_state",
    "agg_category_daily",
    "fact_catalog_snapshot",
    "chg_product_event",
    "chg_price_change",
    "fact_price_snapshot",
)


def untrusted_source_codes(session: Session) -> dict[str, str]:
    """Map of source code -> trust level for every source below ``real``.

    The level is resolved from the code registry for bundled sources and from
    the stored configuration for dashboard-defined ones (falling back to the
    preset the row was created from). The resolved value is written back to the
    dimension row so the API and the warehouse agree on the classification.
    """
    from sqlalchemy import select

    from app.ingestion.base import list_sources
    from app.ingestion.sources.generic_json import preset_data_trust
    from app.models.dimensions import DimSource

    levels: dict[str, str] = {}
    for definition in list_sources():
        levels[definition["code"]] = str(definition.get("data_trust") or DATA_TRUST_REAL)

    for row in session.execute(select(DimSource)).scalars():
        if row.source_code in levels:
            level = levels[row.source_code]
        else:
            config = row.config or {}
            level = str(config.get("data_trust") or preset_data_trust(row.base_url) or DATA_TRUST_REAL)
        levels[row.source_code] = level
        if (row.data_trust or "") != level:
            row.data_trust = level

    return {code: level for code, level in levels.items() if level != DATA_TRUST_REAL}


def _table_columns(session: Session, table: str) -> set[str]:
    from sqlalchemy import inspect

    inspector = inspect(session.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def purge_untrusted(database: str | None = None, *, dry_run: bool = False) -> dict[str, Any]:
    """Delete every warehouse row written by a non-``real`` source.

    Returns a report with the per-table row counts that were removed. With
    ``dry_run=True`` nothing is deleted and the report says what would be.
    """
    report: dict[str, Any] = {
        "database": (database or "postgres").lower(),
        "dry_run": dry_run,
        "sources": {},
        "deleted": {},
        "products_removed": 0,
        "products_repointed": 0,
        "runs_removed": 0,
    }
    with session_scope(database) as session:
        # Refresh the classification from the code registry first: the trust
        # level is a property of the source, and the dimension row may predate
        # the classification entirely.
        from app.etl.bootstrap import sync_registry_sources

        sync_registry_sources(session)
        session.flush()

        untrusted = untrusted_source_codes(session)
        if not untrusted:
            return report
        report["sources"] = untrusted
        codes = list(untrusted)

        # Everything is computed *before* the first delete: the "which products
        # and runs are left without observations" questions can only be asked
        # against the intact warehouse.
        counts: dict[str, int] = {}
        for table in _SOURCE_SCOPED_TABLES:
            columns = _table_columns(session, table)
            if "source_code" not in columns:
                continue
            count = (
                session.execute(
                    sa.select(sa.func.count())
                    .select_from(sa.text(table))
                    .where(sa.column("source_code").in_(codes))
                ).scalar()
                or 0
            )
            if count:
                counts[table] = count
        product_ids = _products_without_observations(session, codes)
        run_ids = _runs_without_references(session, codes)

        report["deleted"] = counts
        report["products_removed"] = len(product_ids)
        report["runs_removed"] = len(run_ids)

        if dry_run:
            return report

        for table in counts:
            session.execute(
                sa.text(f"DELETE FROM {table} WHERE source_code IN :codes").bindparams(
                    sa.bindparam("codes", expanding=True)
                ),
                {"codes": codes},
            )
        if product_ids:
            _delete_products(session, product_ids)
        report["products_repointed"] = _repair_product_sources(session, codes)
        if run_ids:
            # Every table that points at a run has to go first: the run row is
            # the parent of all of them, and a leftover child blocks the
            # delete. `fact_catalog_snapshot` is the one that is easy to miss
            # because its `source_code` is often NULL.
            for table in (
                "fact_price_snapshot",
                "chg_price_change",
                "chg_product_event",
                "fact_catalog_snapshot",
                "dq_rule_result",
                "ingestion_http_log",
                "stg_raw_observation",
            ):
                columns = _table_columns(session, table)
                if "run_id" not in columns:
                    continue
                session.execute(
                    sa.text(f"DELETE FROM {table} WHERE run_id IN :ids").bindparams(
                        sa.bindparam("ids", expanding=True)
                    ),
                    {"ids": run_ids},
                )
            session.execute(
                sa.text("DELETE FROM etl_run WHERE run_id IN :ids").bindparams(
                    sa.bindparam("ids", expanding=True)
                ),
                {"ids": run_ids},
            )

        # Keep the dimension rows (they document the removal) but stop the
        # sources from being picked up again, and zero the counters so the
        # Sources screen does not claim records that no longer exist.
        from app.models.dimensions import DimSource

        for row in session.execute(sa.select(DimSource).where(DimSource.source_code.in_(codes))).scalars():
            row.enabled = False
            row.total_records = 0
            row.success_rate_pct = 0.0
            row.avg_duration_seconds = 0.0

    log.info("purged untrusted sources from %s: %s", report["database"], report["deleted"])
    return report


def _products_without_observations(session: Session, codes: list[str]) -> list[int]:
    """Product ids whose every observation came from an untrusted source."""
    from app.models.dimensions import DimProduct

    trusted_observed: sa.Select[Any] = (
        sa.select(sa.column("product_id"))
        .select_from(sa.text("fact_price_snapshot"))
        .distinct()
        .where(sa.column("source_code").not_in(codes))
    )
    statement = (
        sa.select(DimProduct.product_id)
        .where(DimProduct.source_code.in_(codes))
        .where(~sa.column("product_id").in_(trusted_observed))
    )
    return list(session.execute(statement).scalars())


def _repair_product_sources(session: Session, codes: list[str]) -> int:
    """Re-point surviving products at a source they really came from.

    A product keeps the source that first produced it. When that source is
    untrusted but the product was later seen by a trusted one, the product
    survives the purge - yet its ``dim_product.source_code`` would still name
    the source that was just removed. The column is repaired to the trusted
    source the product was actually observed at, so the dashboard never
    attributes a row to a feed that no longer holds data.
    """
    if not codes:
        return 0
    from app.models.dimensions import DimProduct

    statement = sa.select(DimProduct).where(DimProduct.source_code.in_(codes))
    repaired = 0
    for product in session.execute(statement).scalars():
        replacement = session.execute(
            sa.select(sa.column("source_code"))
            .select_from(sa.text("fact_price_snapshot"))
            .where(sa.column("product_id") == product.product_id)
            .where(sa.column("source_code").not_in(codes))
            .limit(1)
        ).scalar()
        if replacement:
            product.source_code = replacement
            repaired += 1
    return repaired


def _delete_products(session: Session, product_ids: list[int]) -> None:
    """Remove products and the rows that depend on them."""
    for table in (
        "fact_price_snapshot",
        "chg_price_change",
        "chg_product_event",
        "fact_catalog_snapshot",
    ):
        session.execute(
            sa.text(f"DELETE FROM {table} WHERE product_id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": product_ids},
        )
    session.execute(
        sa.text("DELETE FROM dim_product WHERE product_id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ),
        {"ids": product_ids},
    )


def _runs_without_references(session: Session, codes: list[str]) -> list[str]:
    """Runs whose every observation came from an untrusted source.

    A run that touched only untrusted feeds describes work that never
    contributed to the market picture, so its history row goes too. A run with
    no observations at all (a failed or rejected run) is *real* operational
    history and is kept.
    """
    trusted_any: sa.Select[Any] = (
        sa.select(sa.column("run_id"))
        .select_from(sa.text("fact_price_snapshot"))
        .distinct()
        .where(sa.column("source_code").not_in(codes))
    )
    statement = (
        sa.select(sa.distinct(sa.column("run_id")))
        .select_from(sa.text("fact_price_snapshot"))
        .where(sa.column("source_code").in_(codes))
        .where(~sa.column("run_id").in_(trusted_any))
    )
    return list(session.execute(statement).scalars())


__all__ = ["purge_untrusted", "untrusted_source_codes"]
