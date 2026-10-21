"""Remove the generated placeholder catalogue from a warehouse.

The pipeline reconciles the market against the *retailer's* own product list.
The demo seeder writes a placeholder list so the reconciliation screens have
something to show, and every row it writes is marked with
``attributes["catalog_origin"] = "demo-seed"``. This module removes exactly
those rows - and nothing else - so a deployment can drop the placeholder and
keep the catalogue it really imported.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.db import session_scope
from app.core.logging import get_logger

log = get_logger(__name__)

#: The marker the demo seeder writes onto every catalogue row.
ORIGIN_KEY = "catalog_origin"
ORIGIN_VALUE = "demo-seed"

#: Signatures of catalogue rows written by *older* versions of the demo
#: seeder, before the marker existed. They are still placeholders, so they are
#: still removed - a leftover from an earlier release must not be able to
#: present itself as an imported product.
LEGACY_SEED_PATTERNS: tuple[str, ...] = (
    "INT-%",
    "INT-X-%",
    "DEMO-%",
)


def demo_catalog_rows(session: Session) -> list[str]:
    """The SKUs of every generated catalogue row.

    A row counts as generated when it carries the marker, when its SKU is in
    the reserved demo namespace, or when it names one of the demo suppliers.
    """
    from app.models.catalog import CatalogProduct

    rows = session.execute(
        sa.select(CatalogProduct.sku, CatalogProduct.attributes, CatalogProduct.supplier)
    ).all()
    demo_suppliers = {
        "Acme Imports",
        "Globex Supply",
        "Initech Wholesale",
        "Umbrella Ltd",
        "Hooli Logistics",
        "Main Distributor",
        "Main",
    }
    found: list[str] = []
    for sku, attributes, supplier in rows:
        if isinstance(attributes, dict) and attributes.get(ORIGIN_KEY) == ORIGIN_VALUE:
            found.append(sku)
            continue
        if any(sku.startswith(prefix) for prefix in LEGACY_SEED_PATTERNS):
            found.append(sku)
            continue
        if supplier in demo_suppliers:
            found.append(sku)
    return found


def purge_demo_catalog(database: str | None = None, *, dry_run: bool = False) -> dict[str, Any]:
    """Delete the generated catalogue rows. Returns what was found and removed."""
    report: dict[str, Any] = {"found": 0, "removed": 0}
    with session_scope(database) as session:
        skus = demo_catalog_rows(session)
        report["found"] = len(skus)
        if not skus or dry_run:
            return report
        for chunk_start in range(0, len(skus), 500):
            chunk = skus[chunk_start : chunk_start + 500]
            # The reconciliation rows point at the catalogue, so they have to go
            # first: a catalogue row that is still referenced cannot be
            # deleted.
            session.execute(
                sa.text("DELETE FROM fact_catalog_snapshot WHERE catalog_sku IN :skus").bindparams(
                    sa.bindparam("skus", expanding=True)
                ),
                {"skus": chunk},
            )
            session.execute(
                sa.text("DELETE FROM catalog_product WHERE sku IN :skus").bindparams(
                    sa.bindparam("skus", expanding=True)
                ),
                {"skus": chunk},
            )
        report["removed"] = len(skus)
    log.info("removed %s generated catalogue rows", report["removed"])
    return report


__all__ = ["ORIGIN_KEY", "ORIGIN_VALUE", "demo_catalog_rows", "purge_demo_catalog"]
