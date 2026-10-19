"""Dataset export endpoints: CSV, Excel and JSON downloads for every list surface.

The dashboard exposes a download button wherever there is a table; this router is
the single implementation behind all of them.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response

from app.api.deps import DbSession, ReadUser
from app.services import exporter

router = APIRouter(prefix="/export", tags=["export"])


def _query_filters(request: Request, dataset: exporter.Dataset) -> dict[str, Any]:
    """Collect only the filters a dataset declares, ignoring page/sort noise."""
    return {name: request.query_params[name] for name in dataset.filters if name in request.query_params}


@router.get("/datasets", summary="List exportable datasets with their supported filters")
def datasets(_user: ReadUser) -> dict[str, Any]:
    items = exporter.list_datasets()
    groups: dict[str, list[str]] = {}
    for item in items:
        groups.setdefault(item["group"], []).append(item["key"])
    return {
        "total": len(items),
        "formats": ["csv", "xlsx", "json"],
        "max_rows": exporter.MAX_ROWS,
        "default_rows": exporter.DEFAULT_ROWS,
        "groups": groups,
        "datasets": items,
    }


@router.get(
    "/{dataset}.csv",
    summary="Download a dataset as CSV",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
def export_csv(
    request: Request,
    session: DbSession,
    _user: ReadUser,
    dataset: str,
    limit: Annotated[int, Query(ge=1, le=exporter.MAX_ROWS)] = exporter.DEFAULT_ROWS,
) -> Response:
    spec = exporter.get_dataset(dataset)
    _, rows = exporter.fetch_rows(session, dataset, filters=_query_filters(request, spec), row_limit=limit)
    body = exporter.to_csv(rows)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{exporter.filename_for(spec, "csv")}"',
            "X-Row-Count": str(len(rows)),
            "X-Export-Limit": str(limit),
        },
    )


@router.get(
    "/{dataset}.json",
    summary="Download a dataset as JSON (with an export envelope)",
    response_class=Response,
    responses={200: {"content": {"application/json": {}}}},
)
def export_json(
    request: Request,
    session: DbSession,
    _user: ReadUser,
    dataset: str,
    limit: Annotated[int, Query(ge=1, le=exporter.MAX_ROWS)] = exporter.DEFAULT_ROWS,
) -> Response:
    spec = exporter.get_dataset(dataset)
    _, rows = exporter.fetch_rows(session, dataset, filters=_query_filters(request, spec), row_limit=limit)
    body = exporter.to_json(rows, spec, limit)
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{exporter.filename_for(spec, "json")}"',
            "X-Row-Count": str(len(rows)),
            "X-Export-Limit": str(limit),
        },
    )


@router.get(
    "/{dataset}.xlsx",
    summary="Download a dataset as an Excel workbook",
    response_class=Response,
    responses={200: {"content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}}},
)
def export_xlsx(
    request: Request,
    session: DbSession,
    _user: ReadUser,
    dataset: str,
    limit: Annotated[int, Query(ge=1, le=exporter.MAX_ROWS)] = exporter.DEFAULT_ROWS,
) -> Response:
    spec = exporter.get_dataset(dataset)
    _, rows = exporter.fetch_rows(session, dataset, filters=_query_filters(request, spec), row_limit=limit)
    body = exporter.to_xlsx(rows)
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{exporter.filename_for(spec, "xlsx")}"',
            "X-Row-Count": str(len(rows)),
            "X-Export-Limit": str(limit),
        },
    )


@router.get("/{dataset}", summary="Preview a dataset as JSON without downloading")
def preview(
    request: Request,
    session: DbSession,
    _user: ReadUser,
    dataset: str,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 50,
) -> dict[str, Any]:
    spec = exporter.get_dataset(dataset)
    _, rows = exporter.fetch_rows(session, dataset, filters=_query_filters(request, spec), row_limit=limit)
    return {
        "dataset": spec.key,
        "title": spec.title,
        "row_count": len(rows),
        "columns": list(rows[0].keys()) if rows else list(spec.columns),
        "rows": rows,
    }


__all__ = ["router"]
