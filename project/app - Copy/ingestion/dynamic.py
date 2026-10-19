"""Dashboard-defined sources: ``dim_source`` rows that behave like registry entries.

Code-defined sources live in :mod:`app.ingestion.sources` and are registered at
import time. Rows created through ``POST /sources`` instead carry
``config.adapter == "generic_json"`` and materialise on demand as
:class:`GenericJsonSource`. Nothing here mutates the global registry, so a row
edit takes effect on the next resolution with no restart, and tests cannot leak
a source into each other.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import SourceNotFoundError
from app.ingestion.base import ProductSource, get_source, get_source_class
from app.ingestion.sources.generic_json import ADAPTER_NAME, GenericJsonSource
from app.models.dimensions import DimSource

#: Provenance marker served alongside every source definition.
MANAGED_CODE = "code"
MANAGED_DATABASE = "database"


def is_dynamic_row(row: DimSource | None) -> bool:
    """True when the row was created through the dashboard, not in code."""
    config = (row.config if row is not None else None) or {}
    return isinstance(config, dict) and config.get("adapter") == ADAPTER_NAME


def dynamic_rows(session: Session, *, enabled_only: bool = False) -> list[DimSource]:
    """Every dashboard-defined source row, ordered by code for stable output."""
    from sqlalchemy import select

    statement = select(DimSource).order_by(DimSource.source_code)
    rows = list(session.execute(statement).scalars())
    selected = [row for row in rows if is_dynamic_row(row)]
    if enabled_only:
        selected = [row for row in selected if row.enabled]
    return selected


def dynamic_definitions(session: Session) -> list[dict[str, Any]]:
    """Health-check dicts for dashboard rows, shaped like registry entries."""
    definitions = []
    for row in dynamic_rows(session):
        payload = GenericJsonSource.from_row(row).health_check()
        payload["managed"] = MANAGED_DATABASE
        definitions.append(payload)
    return definitions


def enabled_dynamic_codes(session: Session) -> list[str]:
    """Codes the pipeline auto-selects alongside enabled registry sources."""
    return [row.source_code for row in dynamic_rows(session, enabled_only=True) if row.terms_allowed]


def resolve_source(
    session: Session,
    code: str,
    run_id: str | None = None,
    client: Any | None = None,
) -> ProductSource:
    """Instantiate a source by code, from the registry or from the database.

    Registry classes win on a code clash, so a dashboard row can never shadow
    (or break) a bundled source; creating such a code is rejected with 409.
    """
    try:
        get_source_class(code)
    except SourceNotFoundError:
        row = session.get(DimSource, code)
        if row is None or not is_dynamic_row(row):
            raise
        return GenericJsonSource.from_row(row, run_id=run_id, client=client)
    return get_source(code, run_id=run_id, client=client)


__all__ = [
    "MANAGED_CODE",
    "MANAGED_DATABASE",
    "dynamic_definitions",
    "dynamic_rows",
    "enabled_dynamic_codes",
    "is_dynamic_row",
    "resolve_source",
]
