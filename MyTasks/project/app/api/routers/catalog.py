"""Internal catalog endpoints: SKUs, reconciliation results, price-gap analysis."""

from __future__ import annotations

import csv
import io
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Query, Request, UploadFile
from fastapi.responses import PlainTextResponse

from app.api.deps import DbSession, PaginationDep, ReadUser, WriteUser, request_meta
from app.api.schemas import CatalogMatchRead, Page
from app.core.errors import ValidationError
from app.models.app_users import AppAuditLog
from app.models.catalog import CatalogProduct

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/reconciliation", response_model=Page[CatalogMatchRead], summary="Scraped vs internal catalog")
def reconciliation(
    session: DbSession,
    pagination: PaginationDep,
    _user: ReadUser,
    run_id: str | None = None,
    match_status: str | None = None,
    only_mismatches: Annotated[bool, Query()] = False,
) -> Page[CatalogMatchRead]:
    where = ["1 = 1"]
    params: dict[str, Any] = {}
    if run_id:
        where.append("run_id = :run_id")
        params["run_id"] = run_id
    if match_status:
        where.append("match_status = :match_status")
        params["match_status"] = match_status
    if only_mismatches:
        where.append("is_price_mismatch")
    clause = "WHERE " + " AND ".join(where)
    total = (
        session.execute(sa.text(f"SELECT COUNT(*) FROM vw_catalog_reconciliation {clause}"), params).scalar()
        or 0
    )
    rows = (
        session.execute(
            sa.text(
                f"""
            SELECT match_id, run_id, catalog_sku, catalog_name, catalog_brand, catalog_category, catalog_price,
                   supplier, product_id, scraped_name, scraped_brand, scraped_category, scraped_price_usd,
                   price_gap_abs, price_gap_pct, match_status, match_strategy, similarity_score,
                   category_match, brand_match, is_price_mismatch, matched_at
            FROM vw_catalog_reconciliation {clause}
            ORDER BY ABS(COALESCE(price_gap_pct, 0)) DESC
            LIMIT :limit OFFSET :offset
            """
            ),
            {**params, "limit": pagination.page_size, "offset": pagination.offset},
        )
        .mappings()
        .all()
    )
    return Page.build([dict(row) for row in rows], total, pagination.page, pagination.page_size)


@router.get("/products", response_model=Page[dict[str, Any]], summary="Internal catalog SKUs")
def products(
    session: DbSession,
    pagination: PaginationDep,
    _user: ReadUser,
    q: str | None = None,
    status: str | None = None,
) -> Page[dict[str, Any]]:
    where = ["1 = 1"]
    params: dict[str, Any] = {}
    if q:
        where.append("(name LIKE :q OR sku LIKE :q OR brand LIKE :q)")
        params["q"] = f"%{q}%"
    if status:
        where.append("status = :status")
        params["status"] = status
    clause = "WHERE " + " AND ".join(where)
    total = session.execute(sa.text(f"SELECT COUNT(*) FROM catalog_product {clause}"), params).scalar() or 0
    rows = (
        session.execute(
            sa.text(
                f"""
            SELECT sku, name, brand, category, supplier, cost_price, list_price, currency,
                   qty_on_hand, status, product_url, updated_at
            FROM catalog_product {clause}
            ORDER BY sku LIMIT :limit OFFSET :offset
            """
            ),
            {**params, "limit": pagination.page_size, "offset": pagination.offset},
        )
        .mappings()
        .all()
    )
    return Page.build([dict(row) for row in rows], total, pagination.page, pagination.page_size)


@router.get("/summary", summary="Reconciliation KPIs")
def summary(session: DbSession, _user: ReadUser, run_id: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    clause = ""
    if run_id:
        clause = "WHERE run_id = :run_id"
        params["run_id"] = run_id
    totals = (
        session.execute(
            sa.text(
                f"""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN match_status = 'matched' THEN 1 ELSE 0 END) AS matched,
                   SUM(CASE WHEN match_status = 'unmatched' THEN 1 ELSE 0 END) AS unmatched,
                   SUM(CASE WHEN is_price_mismatch THEN 1 ELSE 0 END) AS price_mismatches,
                   ROUND(CAST(AVG(similarity_score) AS DECIMAL(24,6)), 4) AS avg_similarity,
                   ROUND(CAST(AVG(price_gap_pct) AS DECIMAL(24,6)), 2) AS avg_price_gap_pct
            FROM vw_catalog_reconciliation {clause}
            """
            ),
            params,
        )
        .mappings()
        .one()
    )
    by_strategy = (
        session.execute(
            sa.text(
                f"""
            SELECT match_strategy, COUNT(*) AS count FROM vw_catalog_reconciliation {clause}
            GROUP BY match_strategy ORDER BY count DESC
            """
            ),
            params,
        )
        .mappings()
        .all()
    )
    by_supplier = (
        session.execute(
            sa.text(
                f"""
            SELECT supplier, COUNT(*) AS skus, ROUND(CAST(AVG(price_gap_pct) AS DECIMAL(24,6)), 2) AS avg_gap_pct
            FROM vw_catalog_reconciliation {clause}
            GROUP BY supplier ORDER BY skus DESC
            """
            ),
            params,
        )
        .mappings()
        .all()
    )
    return {
        "totals": dict(totals),
        "by_strategy": [dict(row) for row in by_strategy],
        "by_supplier": [dict(row) for row in by_supplier],
        "run_id": run_id,
    }


@router.get("/opportunities", summary="Top pricing opportunities (cheaper / dearer than market)")
def opportunities(
    session: DbSession, _user: ReadUser, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[dict[str, Any]]:
    rows = (
        session.execute(
            sa.text(
                """
            SELECT catalog_sku, catalog_name, supplier, catalog_price, scraped_name, scraped_price_usd,
                   price_gap_abs, price_gap_pct,
                   CASE WHEN price_gap_pct < 0 THEN 'we_are_dearer' ELSE 'we_are_cheaper' END AS position
            FROM vw_catalog_reconciliation
            WHERE is_price_mismatch AND price_gap_pct IS NOT NULL
            ORDER BY ABS(price_gap_pct) DESC LIMIT :limit
            """
            ),
            {"limit": limit},
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


#: Columns accepted by the CSV import, in template order. `sku` and `name` are
#: required; everything else falls back to a safe default per row.
IMPORT_COLUMNS = (
    "sku",
    "name",
    "brand",
    "category",
    "supplier",
    "cost_price",
    "list_price",
    "currency",
    "qty_on_hand",
    "status",
    "product_url",
)

IMPORT_EXAMPLE_ROWS = (
    {
        "sku": "SKU-0001",
        "name": "Example 55 inch 4K TV",
        "brand": "Example",
        "category": "Electronics",
        "supplier": "Main supplier",
        "cost_price": "900",
        "list_price": "1249.99",
        "currency": "USD",
        "qty_on_hand": "12",
        "status": "active",
        "product_url": "https://example.com/sku-0001",
    },
    {
        "sku": "SKU-0002",
        "name": "Example Bluetooth Speaker",
        "brand": "Example",
        "category": "Audio",
        "supplier": "Main supplier",
        "cost_price": "45",
        "list_price": "79.99",
        "currency": "USD",
        "qty_on_hand": "40",
        "status": "active",
        "product_url": "",
    },
)

#: Hard caps so a hostile file cannot exhaust memory: 5 MB on the wire and
#: 5,000 data rows per import. Both are enforced before any row is written.
IMPORT_MAX_BYTES = 5 * 1024 * 1024
IMPORT_MAX_ROWS = 5000


@router.get("/template", summary="Download a catalog-import CSV template")
def import_template(_user: ReadUser) -> PlainTextResponse:
    """Header plus two example rows, so a spreadsheet opens it correctly."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(IMPORT_COLUMNS))
    writer.writeheader()
    for row in IMPORT_EXAMPLE_ROWS:
        writer.writerow(row)
    return PlainTextResponse(
        buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="catalog-template.csv"'},
    )


def _parse_optional_float(raw: str, field: str, line: int) -> float | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        raise ValidationError(f"row {line}: {field} must be a number, got {raw!r}") from None
    if value < 0:
        raise ValidationError(f"row {line}: {field} must be >= 0, got {raw!r}")
    return value


def _parse_optional_int(raw: str, field: str, line: int) -> int:
    text = (raw or "").strip()
    if not text:
        return 0
    try:
        value = int(float(text))
    except ValueError:
        raise ValidationError(f"row {line}: {field} must be a whole number, got {raw!r}") from None
    if value < 0:
        raise ValidationError(f"row {line}: {field} must be >= 0, got {raw!r}")
    return value


@router.post("/import", summary="Bulk upsert internal SKUs from a CSV file")
def import_products(
    file: UploadFile, request: Request, session: DbSession, user: WriteUser
) -> dict[str, Any]:
    """Upsert `catalog_product` rows keyed by `sku`.

    The whole file is validated first and nothing is written when a row is
    invalid beyond the per-row error budget — a half-loaded catalog is worse
    than a rejected file. Successful imports are audited with counts.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise ValidationError("upload a .csv file exported from the template")
    raw = file.file.read(IMPORT_MAX_BYTES + 1)
    if len(raw) > IMPORT_MAX_BYTES:
        raise ValidationError("file exceeds the 5 MB import limit")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationError("file must be UTF-8 encoded CSV") from None
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValidationError("empty CSV: header row is missing")
    headers = [header.strip() for header in reader.fieldnames]
    if "sku" not in headers or "name" not in headers:
        raise ValidationError("header must include at least 'sku' and 'name'")

    created = 0
    updated = 0
    errors: list[str] = []
    staged: list[dict[str, Any]] = []
    for line, record in enumerate(reader, start=2):
        if len(staged) + len(errors) >= IMPORT_MAX_ROWS:
            errors.append(f"row {line}: file exceeds the {IMPORT_MAX_ROWS} row limit")
            break
        try:
            sku = (record.get("sku") or "").strip()
            name = (record.get("name") or "").strip()
            if not sku:
                raise ValidationError(f"row {line}: sku is required")
            if not name:
                raise ValidationError(f"row {line}: name is required")
            if len(sku) > 64:
                raise ValidationError(f"row {line}: sku exceeds 64 characters")
            currency = ((record.get("currency") or "USD").strip() or "USD").upper()
            if len(currency) != 3 or not currency.isalpha():
                raise ValidationError(f"row {line}: currency must be a 3-letter code")
            status = ((record.get("status") or "active").strip() or "active").lower()
            if status not in {"active", "discontinued"}:
                raise ValidationError(f"row {line}: status must be active or discontinued")
            staged.append(
                {
                    "sku": sku,
                    "name": name,
                    "brand": (record.get("brand") or "").strip() or None,
                    "category": (record.get("category") or "").strip() or None,
                    "supplier": (record.get("supplier") or "").strip() or None,
                    "cost_price": _parse_optional_float(record.get("cost_price") or "", "cost_price", line),
                    "list_price": _parse_optional_float(record.get("list_price") or "", "list_price", line),
                    "currency": currency,
                    "qty_on_hand": _parse_optional_int(record.get("qty_on_hand") or "", "qty_on_hand", line),
                    "status": status,
                    "product_url": (record.get("product_url") or "").strip() or None,
                }
            )
        except ValidationError as exc:
            errors.append(str(exc))
            if len(errors) >= 50:
                errors.append("…stopped after 50 row errors; fix the file and retry")
                break

    if errors:
        raise ValidationError(
            f"{len(errors)} row(s) rejected; nothing was imported",
            details={"errors": errors[:50], "valid_rows": len(staged)},
        )

    for row in staged:
        existing = session.get(CatalogProduct, row["sku"])
        if existing is None:
            session.add(CatalogProduct(**row))
            created += 1
        else:
            for key, value in row.items():
                if key != "sku":
                    setattr(existing, key, value)
            updated += 1
    session.flush()
    meta = request_meta(request)
    session.add(
        AppAuditLog(
            user_id=user.user_id,
            user_email=user.email,
            action="catalog.import",
            entity_type="catalog_product",
            entity_id=None,
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
            details={"created": created, "updated": updated, "filename": file.filename},
        )
    )
    session.commit()
    return {
        "filename": file.filename,
        "created": created,
        "updated": updated,
        "total": created + updated,
    }


#: Cap for the full-catalog download so the response stays in memory-safe bounds.
EXPORT_MAX_ROWS = 10000


@router.get("/export.csv", summary="Download every internal SKU as CSV")
def export_products(session: DbSession, _user: ReadUser) -> PlainTextResponse:
    """The exact inverse of the import: same columns, same order, all SKUs."""
    rows = (
        session.execute(
            sa.text(
                """
            SELECT sku, name, brand, category, supplier, cost_price, list_price, currency,
                   qty_on_hand, status, product_url
            FROM catalog_product ORDER BY sku LIMIT :limit
            """
            ),
            {"limit": EXPORT_MAX_ROWS},
        )
        .mappings()
        .all()
    )
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(IMPORT_COLUMNS))
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "sku": row["sku"],
                "name": row["name"],
                "brand": row["brand"] or "",
                "category": row["category"] or "",
                "supplier": row["supplier"] or "",
                "cost_price": row["cost_price"] if row["cost_price"] is not None else "",
                "list_price": row["list_price"] if row["list_price"] is not None else "",
                "currency": row["currency"] or "USD",
                "qty_on_hand": row["qty_on_hand"] if row["qty_on_hand"] is not None else "",
                "status": row["status"] or "active",
                "product_url": row["product_url"] or "",
            }
        )
    return PlainTextResponse(
        buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="catalog-export.csv"'},
    )
