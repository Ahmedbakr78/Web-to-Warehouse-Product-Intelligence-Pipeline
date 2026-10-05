"""Report endpoints: list templates, preview, and export as HTML or PDF."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app.api.deps import DbSession, ReadUser
from app.api.schemas import Message
from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.services import report as reports
from app.services.pdf import available, unavailable_reason

log = get_logger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/templates", summary="Available report templates")
def templates(_user: ReadUser) -> dict[str, Any]:
    return {
        "templates": reports.template_list(),
        "formats": ["html", "pdf", "csv", "json"],
        "pdf_available": available(),
        "pdf_unavailable_reason": "" if available() else unavailable_reason(),
    }


@router.get("/{template}", summary="Preview a report as HTML")
def preview(
    template: str,
    session: DbSession,
    _user: ReadUser,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    horizon: Annotated[int, Query(ge=1, le=60)] = 14,
    product_id: Annotated[int | None, Query(ge=1)] = None,
    sections: Annotated[str | None, Query(description="Comma-separated section keys")] = None,
) -> HTMLResponse:
    """Render the report in the browser.

    Same blocks as the PDF, so what is reviewed on screen is exactly what is exported.
    """
    payload = _build(session, template, days, horizon, product_id, sections)
    return HTMLResponse(reports.render_report(payload))


@router.get("/{template}/data", summary="A report as structured blocks")
def data(
    template: str,
    session: DbSession,
    _user: ReadUser,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    horizon: Annotated[int, Query(ge=1, le=60)] = 14,
    product_id: Annotated[int | None, Query(ge=1)] = None,
    sections: Annotated[str | None, Query()] = None,
) -> JSONResponse:
    """The report's blocks as JSON, for the dashboard's report builder.

    Returned through JSONResponse rather than a response_model: a block's `badge` and
    `caption` fields may hold a lambda, which pydantic cannot serialise. Those keys are
    renderer hints and are stripped here.
    """
    payload = _build(session, template, days, horizon, product_id, sections)
    for block in payload["blocks"]:
        block.pop("badge", None)
    return JSONResponse(json.loads(json.dumps(payload, default=str)))


@router.get("/{template}/pdf", summary="Download a report as PDF")
def pdf(
    template: str,
    session: DbSession,
    _user: ReadUser,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    horizon: Annotated[int, Query(ge=1, le=60)] = 14,
    product_id: Annotated[int | None, Query(ge=1)] = None,
    sections: Annotated[str | None, Query()] = None,
) -> Response:
    if not available():
        # 501 rather than 500: the request was fine, this deployment just cannot
        # render PDFs. The HTML and CSV paths still work.
        return Response(
            content=unavailable_reason(),
            status_code=501,
            media_type="text/plain; charset=utf-8",
        )
    payload = _build(session, template, days, horizon, product_id, sections)
    body = reports.render_report_pdf(payload)
    return Response(
        content=body,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{template}-report.pdf"',
            "Content-Length": str(len(body)),
        },
    )


@router.post("/{template}/queue", response_model=Message, summary="Render a PDF in the background")
def queue_pdf(
    template: str,
    session: DbSession,
    user: ReadUser,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    product_id: Annotated[int | None, Query(ge=1)] = None,
) -> Message:
    """Enqueue the render so a slow WeasyPrint pass never blocks a request."""
    if template not in reports.TEMPLATE_KEYS:
        raise ValidationError(f"unknown template '{template}'; available: {', '.join(reports.TEMPLATE_KEYS)}")
    from app.jobs import queue

    handle = queue.enqueue(
        session,
        "report_pdf",
        {"template": template, "days": days, "product_id": product_id},
        requested_by=user.user_id,
        requested_by_email=user.email,
    )
    return Message(
        message=f"PDF queued as {handle.job_key}",
        detail={
            "job_id": handle.job_id,
            "job_key": handle.job_key,
            "href": f"/api/v1/jobs/{handle.job_key}",
        },
    )


def _build(
    session,
    template: str,
    days: int,
    horizon: int,
    product_id: int | None,
    sections: str | None,
) -> dict[str, Any]:
    if template not in reports.TEMPLATE_KEYS:
        raise ValidationError(f"unknown template '{template}'; available: {', '.join(reports.TEMPLATE_KEYS)}")
    wanted = [item.strip() for item in sections.split(",") if item.strip()] if sections else None
    spec = reports.TEMPLATES[template]
    if spec.get("requires_product") and product_id is None:
        raise ValidationError(f"template '{template}' requires a product_id")
    return reports.build_report(
        session, template, days=days, horizon=horizon, product_id=product_id, sections=wanted
    )


__all__ = ["router"]
