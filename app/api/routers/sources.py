"""Source registry endpoints, plus dashboard-managed source onboarding.

Code-defined sources ship in :mod:`app.ingestion.sources`. Rows created through
``POST /sources`` instead carry ``config.adapter == "generic_json"`` and are
materialised on demand (see :mod:`app.ingestion.dynamic`), so the dashboard can
onboard a new JSON feed without a deploy. Either way the same compliance gates
apply: SSRF-safe URL, robots.txt verdict, and an explicit terms confirmation.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.api.deps import DbSession, ReadUser, SourceManagerUser, WriteUser
from app.api.schemas import SourceCheckRequest, SourceCreate, SourceUpdate
from app.core.config import settings
from app.core.errors import ConflictError, SourceNotFoundError, ValidationError
from app.ingestion.base import get_source_class, list_sources
from app.ingestion.dynamic import MANAGED_CODE, MANAGED_DATABASE, is_dynamic_row, resolve_source
from app.ingestion.robots import get_robots_cache
from app.ingestion.sources.generic_json import ADAPTER_NAME, PAGINATION_STYLES, PRESETS, get_path
from app.models.dimensions import DimSource

router = APIRouter(prefix="/sources", tags=["sources"])


def _definition_payload(definition: dict[str, Any], managed: str) -> dict[str, Any]:
    payload = dict(definition)
    payload["managed"] = managed
    return payload


@router.get("", summary="Registered sources with compliance metadata")
def sources(session: DbSession, _user: ReadUser) -> list[dict[str, Any]]:
    """Registry classes plus dashboard-defined rows, ordered by code."""
    return list_sources(session)


@router.get("/presets", summary="Ready-made mappings for well-known free endpoints")
def presets(_user: ReadUser) -> dict[str, Any]:
    """Field maps the *Add source* form offers as one-click starting points."""
    return {"presets": PRESETS, "pagination_styles": list(PAGINATION_STYLES)}


@router.get("/robots", summary="robots.txt decisions cached by the ingestion layer")
def robots(_user: ReadUser) -> dict[str, Any]:
    cache = get_robots_cache()
    return {"stats": dict(cache.stats), "user_agent": cache.user_agent, "ttl_seconds": cache.ttl_seconds}


def _safe_url(raw_url: str) -> str:
    """SSRF guard shared with webhooks: only public http(s) endpoints pass."""
    from app.services.webhooks import WebhookError, validate_target_url

    try:
        return validate_target_url(raw_url)
    except WebhookError as exc:
        raise ValidationError(f"unsafe base_url: {exc}") from exc


def _robots_verdict(url: str) -> dict[str, Any]:
    decision = get_robots_cache().can_fetch(url, settings.ingest_user_agent)
    return {
        "allowed": decision.allowed,
        "rule": decision.rule,
        "crawl_delay": decision.crawl_delay,
        "robots_url": f"{url.rsplit('/', 1)[0] if '://' not in url else _origin(url)}/robots.txt",
    }


def _origin(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _sniff_shape(url: str, items_path: str) -> dict[str, Any]:
    """One bounded GET describing the JSON shape, so the form can pre-fill.

    Read-only and side-effect free: no rows are written, no audit is recorded.
    Anything unexpected (non-JSON, timeout, huge body) is reported, never raised.
    """
    try:
        with httpx.Client(
            timeout=12.0, follow_redirects=True, headers={"User-Agent": settings.ingest_user_agent}
        ) as client:
            response = client.get(url)
    except Exception as exc:  # noqa: BLE001 - the verdict must survive any transport failure
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if response.status_code >= 400:
        return {"ok": False, "error": f"HTTP {response.status_code}"}
    try:
        payload = response.json()
    except Exception:
        return {"ok": False, "error": "response is not JSON"}
    top_keys = sorted(payload.keys()) if isinstance(payload, dict) else []
    items = get_path(payload, items_path)
    if isinstance(items, dict):
        items = [items]
    sample_keys: list[str] = []
    first: dict[str, Any] | None = None
    count = 0
    if isinstance(items, list):
        count = len(items)
        for entry in items:
            if isinstance(entry, dict):
                first = entry
                sample_keys = sorted(str(key) for key in entry)[:40]
                break
    return {
        "ok": True,
        "status_code": response.status_code,
        "top_level_keys": top_keys[:40],
        "is_list": isinstance(items, list),
        "item_count": count,
        "item_keys": sample_keys,
        "sample": first,
    }


@router.post("/check", summary="Compliance pre-check for a candidate source URL")
def check_source(payload: SourceCheckRequest, _user: WriteUser) -> dict[str, Any]:
    """Robots verdict plus JSON shape sniff. Writes nothing; the form calls this
    before *Save* so a blocked or non-JSON endpoint fails fast with reasons."""
    url = _safe_url(payload.base_url)
    verdict = _robots_verdict(url)
    shape = _sniff_shape(url, payload.items_path)
    reasons: list[str] = []
    if not verdict["allowed"]:
        reasons.append(f"robots.txt forbids fetching ({verdict['rule']})")
    if not shape.get("ok"):
        reasons.append(f"shape sniff failed: {shape.get('error')}")
    elif not shape.get("is_list"):
        reasons.append(f"items_path '{payload.items_path}' did not resolve to a list")
    elif not shape.get("item_count"):
        reasons.append("the endpoint returned an empty list")
    suggested_delay = verdict["crawl_delay"] or 1.0
    return {
        "url": url,
        "allowed": verdict["allowed"] and not reasons,
        "robots": verdict,
        "shape": shape,
        "suggested_min_delay_seconds": suggested_delay,
        "reasons": reasons,
    }


def _row_payload(row: DimSource) -> dict[str, Any]:
    return {
        "source_code": row.source_code,
        "name": row.name,
        "kind": row.kind,
        "base_url": row.base_url,
        "terms_url": row.terms_url,
        "license_note": row.license_note,
        "rate_limit_per_minute": row.rate_limit_per_minute,
        "min_delay_seconds": row.min_delay_seconds,
        "enabled": row.enabled,
        "terms_allowed": row.terms_allowed,
        "managed": MANAGED_DATABASE,
        "config": row.config or {},
    }


@router.post("", summary="Register a dashboard-defined JSON source", status_code=201)
def create_source(payload: SourceCreate, session: DbSession, _user: SourceManagerUser) -> dict[str, Any]:
    """Create a source without a deploy. The server re-checks robots itself;
    a forbidden endpoint is rejected even if the pre-check was skipped."""
    try:
        get_source_class(payload.code)
    except SourceNotFoundError:
        pass
    else:
        raise ConflictError(f"source code '{payload.code}' is already a bundled source")
    if session.get(DimSource, payload.code) is not None:
        raise ConflictError(f"source code '{payload.code}' already exists")
    if not payload.terms_confirmed:
        raise ValidationError(
            "terms_confirmed must be true: confirm the site's terms permit automated access"
        )

    url = _safe_url(payload.base_url)
    verdict = _robots_verdict(url)
    if not verdict["allowed"]:
        raise ValidationError(
            f"robots.txt forbids fetching {url} ({verdict['rule']}); this pipeline does not onboard blocked sources"
        )

    mapping = payload.mapping
    row = DimSource(
        source_code=payload.code,
        name=payload.name,
        kind="api",
        base_url=url,
        terms_url=payload.terms_url,
        license_note=payload.license_note,
        rate_limit_per_minute=payload.rate_limit_per_minute,
        min_delay_seconds=max(payload.min_delay_seconds, float(verdict["crawl_delay"] or 0.0)),
        enabled=payload.enabled,
        terms_allowed=True,
        config={
            "adapter": ADAPTER_NAME,
            "items_path": mapping.items_path,
            "id_field": mapping.id_field,
            "fields": dict(mapping.fields),
            "pagination": mapping.pagination.model_dump(),
            "params": dict(mapping.params),
            **({"url_template": mapping.url_template} if mapping.url_template else {}),
            "currency": mapping.currency,
        },
    )
    session.add(row)
    session.flush()
    return _row_payload(row)


def _dynamic_row_or_404(session: Session, code: str) -> DimSource:
    row = session.get(DimSource, code)
    if row is None or not is_dynamic_row(row):
        raise SourceNotFoundError(
            f"no dashboard-managed source '{code}'",
            details={"hint": "bundled sources are defined in code and cannot be edited here"},
        )
    return row


@router.patch("/{code}", summary="Edit a dashboard-defined source")
def update_source(
    code: str, payload: SourceUpdate, session: DbSession, _user: SourceManagerUser
) -> dict[str, Any]:
    """Only dashboard rows are editable; bundled sources live in version control."""
    row = _dynamic_row_or_404(session, code)
    config = dict(row.config or {})
    if payload.name is not None:
        row.name = payload.name
    if payload.base_url is not None:
        url = _safe_url(payload.base_url)
        verdict = _robots_verdict(url)
        if not verdict["allowed"]:
            raise ValidationError(f"robots.txt forbids fetching {url} ({verdict['rule']})")
        row.base_url = url
        row.min_delay_seconds = max(row.min_delay_seconds or 0.0, float(verdict["crawl_delay"] or 0.0))
    if payload.terms_url is not None:
        row.terms_url = payload.terms_url
    if payload.license_note is not None:
        row.license_note = payload.license_note
    if payload.rate_limit_per_minute is not None:
        row.rate_limit_per_minute = payload.rate_limit_per_minute
    if payload.min_delay_seconds is not None:
        row.min_delay_seconds = payload.min_delay_seconds
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.terms_confirmed is not None:
        row.terms_allowed = payload.terms_confirmed
    if payload.mapping is not None:
        mapping = payload.mapping
        config.update(
            {
                "adapter": ADAPTER_NAME,
                "items_path": mapping.items_path,
                "id_field": mapping.id_field,
                "fields": dict(mapping.fields),
                "pagination": mapping.pagination.model_dump(),
                "params": dict(mapping.params),
                "currency": mapping.currency,
            }
        )
        if mapping.url_template:
            config["url_template"] = mapping.url_template
        else:
            config.pop("url_template", None)
        row.config = config
    session.flush()
    return _row_payload(row)


@router.delete("/{code}", summary="Delete a dashboard-defined source")
def delete_source(code: str, session: DbSession, _user: SourceManagerUser) -> dict[str, Any]:
    """Only dashboard rows that never ran can be deleted; anything with history
    must be disabled instead so warehouse lineage stays intact."""
    row = _dynamic_row_or_404(session, code)
    if (row.total_runs or 0) > 0:
        raise ConflictError(
            f"source '{code}' has {row.total_runs} recorded run(s); disable it instead of deleting"
        )
    session.delete(row)
    session.flush()
    return {"deleted": code}


@router.get("/{code}", summary="One source definition")
def source(code: str, session: DbSession, _user: ReadUser) -> dict[str, Any]:
    try:
        payload = get_source_class(code)().health_check()
        return _definition_payload(payload, MANAGED_CODE)
    except SourceNotFoundError:
        pass
    row = session.get(DimSource, code)
    if row is None or not is_dynamic_row(row):
        raise SourceNotFoundError(f"unknown source '{code}'")
    from app.ingestion.sources.generic_json import GenericJsonSource

    return _definition_payload(GenericJsonSource.from_row(row).health_check(), MANAGED_DATABASE)


@router.get("/{code}/preview", summary="Fetch a few raw records without loading them")
def preview(code: str, session: DbSession, _user: ReadUser, limit: int = 5) -> dict[str, Any]:
    from app.ingestion.base import transform_product

    source = resolve_source(session, code)
    records = []
    try:
        for index, raw in enumerate(source.fetch(limit=limit)):
            if index >= limit:
                break
            record = transform_product(raw)
            records.append(
                {
                    "source_product_id": record.source_product_id,
                    "canonical_name": record.canonical_name,
                    "raw_name": record.raw_name,
                    "category": record.category,
                    "price": record.price,
                    "currency": record.currency,
                    "price_usd": record.price_usd,
                    "rating": record.rating,
                    "availability": record.availability,
                    "quality_flags": record.quality_flags,
                    "is_valid": record.is_valid,
                    "reject_reason": record.reject_reason,
                    "product_url": record.product_url,
                }
            )
    finally:
        source.close()
    return {
        "code": code,
        "requested": limit,
        "returned": len(records),
        "http_calls": source.http_calls,
        "errors": source.errors,
        "records": records,
    }
