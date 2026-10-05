"""Forecasting, anomaly detection and price prediction endpoints."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Query

from app.analytics import forecast as engine
from app.api.deps import DbSession, ReadUser
from app.core.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/forecast", tags=["forecasting"])


@router.get("/{product_id}", summary="Price forecast with measured accuracy")
def forecast_product(
    product_id: int,
    session: DbSession,
    _user: ReadUser,
    horizon: Annotated[int, Query(ge=1, le=90, description="Days to project forward")] = 14,
    days: Annotated[int, Query(ge=7, le=730, description="History to fit on")] = 120,
) -> dict[str, Any]:
    """Holt-Winters projection for one product.

    The accuracy metrics come from a genuine holdout backtest, not from the fit that
    produced the forecast, so a poor model shows up as a poor MAPE instead of being
    quietly hidden.
    """
    exists = session.execute(
        sa.text("SELECT COUNT(*) FROM vw_product_current WHERE product_id = :pid"), {"pid": product_id}
    ).scalar()
    if not exists:
        return {"product_id": product_id, "points": [], "reason": "product not found"}

    result = engine.forecast_product(session, product_id, horizon=horizon, days=days)
    payload = result.as_dict()
    row = (
        session.execute(
            sa.text("SELECT canonical_name, category_name FROM vw_product_current WHERE product_id = :pid"),
            {"pid": product_id},
        )
        .mappings()
        .first()
    )
    if row:
        payload["name"] = row["canonical_name"]
        payload["category"] = row["category_name"]
    return payload


@router.get("/{product_id}/anomalies", summary="Anomalous price observations")
def anomalies_for_product(
    product_id: int,
    session: DbSession,
    _user: ReadUser,
    days: Annotated[int, Query(ge=7, le=730)] = 120,
    window: Annotated[int, Query(ge=5, le=180, description="Local comparison window")] = 28,
    threshold: Annotated[float, Query(ge=1.0, le=20.0)] = 3.5,
    method: Annotated[str, Query(description="mad | std | iqr")] = "mad",
) -> dict[str, Any]:
    found = engine.anomalies_for_product(
        session, product_id, days=days, window=window, threshold=threshold, method=method
    )
    return {
        "product_id": product_id,
        "method": method,
        "threshold": threshold,
        "window": window,
        "count": len(found),
        "anomalies": [item.as_dict() for item in found],
    }


@router.get("/products/anomalies", summary="Anomalies across every product, most extreme first")
def anomalies_across_products(
    session: DbSession,
    _user: ReadUser,
    days: Annotated[int, Query(ge=7, le=730)] = 120,
    threshold: Annotated[float, Query(ge=1.0, le=20.0)] = 3.5,
    method: Annotated[str, Query(description="mad | std | iqr")] = "mad",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict[str, Any]:
    found = engine.anomalies_all(session, days=days, threshold=threshold, method=method)
    return {
        "method": method,
        "threshold": threshold,
        "total": len(found),
        "by_severity": {
            level: sum(1 for item in found if item.severity == level)
            for level in ("critical", "high", "medium", "low")
        },
        "by_direction": {
            direction: sum(1 for item in found if item.direction == direction)
            for direction in ("spike", "drop")
        },
        "anomalies": [item.as_dict() for item in found[:limit]],
    }


@router.get("/{product_id}/predict-price", summary="Recommended price with its reasoning")
def predict_price(
    product_id: int,
    session: DbSession,
    _user: ReadUser,
    horizon: Annotated[int, Query(ge=1, le=60)] = 14,
    days: Annotated[int, Query(ge=7, le=730)] = 120,
    elasticity: Annotated[float, Query(ge=-5.0, le=5.0, description="Price elasticity of demand")] = -1.4,
) -> dict[str, Any]:
    """A recommended price, with every step of the reasoning returned alongside it.

    The recommendation is damped whenever the projected move exceeds the break-even
    implied by the target margin, so a volatile series cannot talk the system into an
    unrealistic price.
    """
    points = engine.load_series(session, product_id, days=days)
    if len(points) < 3:
        return {
            "product_id": product_id,
            "recommended_price": None,
            "reason": f"only {len(points)} observation(s); at least 3 are needed",
        }

    values = [point.value for point in points]
    fitted = engine.damped_holt_winters(values, horizon)
    prediction = engine.predict_price(values, fitted.values, elasticity=elasticity)
    prediction.product_id = product_id

    payload = prediction.as_dict()
    payload["horizon"] = horizon
    payload["history_points"] = len(values)
    payload["seasonal_indices"] = {
        str(slot): round(value, 4) for slot, value in sorted(fitted.seasonal_indices.items())
    }
    return payload


@router.get("/{product_id}/seasonality", summary="Weekly price profile")
def seasonality(
    product_id: int, session: DbSession, _user: ReadUser, days: Annotated[int, Query(ge=14, le=730)] = 120
) -> dict[str, Any]:
    """Average price per weekday, for a heatmap on the product screen."""
    points = engine.load_series(session, product_id, days=days)
    profile = engine.seasonality_profile([point.value for point in points])
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return {
        "product_id": product_id,
        "observations": len(points),
        "weekdays": [
            {
                "slot": slot,
                "name": names[slot % 7],
                **stats,
            }
            for slot, stats in sorted(profile.items())
        ],
    }


@router.get("/category/{category}/elasticity", summary="Demand elasticity for a category")
def elasticity(
    category: str, session: DbSession, _user: ReadUser, days: Annotated[int, Query(ge=7, le=730)] = 120
) -> dict[str, Any]:
    return engine.elasticity_for_category(session, category, days=days)


@router.get("/backtest", summary="Model accuracy across every modelled product")
def backtest_summary(
    session: DbSession,
    _user: ReadUser,
    horizon: Annotated[int, Query(ge=1, le=60)] = 14,
    min_points: Annotated[int, Query(ge=10, le=200)] = 21,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> dict[str, Any]:
    """How accurate the model actually is, across the catalogue.

    Reporting this honestly matters more than a single favourable number: a model
    that is only right for some products should be visible as such.
    """
    scored: list[dict[str, Any]] = []
    for product_id, name in engine.product_ids_with_history(session, min_points=min_points, limit=limit):
        points = engine.load_series(session, product_id)
        values = [point.value for point in points]
        metrics = engine.backtest(values, horizon, holdout=min(7, max(2, len(values) // 5)))
        mape = metrics.get("mape_pct")
        mae = metrics.get("mae")
        rmse = metrics.get("rmse")
        if mape is None or mae is None or rmse is None:
            continue
        scored.append(
            {
                "product_id": product_id,
                "name": name,
                "observations": len(values),
                "mape_pct": round(mape, 3),
                "mae": round(mae, 4),
                "rmse": round(rmse, 4),
            }
        )

    scored.sort(key=lambda row: row["mape_pct"])
    mapes = [row["mape_pct"] for row in scored]
    return {
        "model": "damped_holt_winters",
        "horizon": horizon,
        "evaluated": len(scored),
        "mean_mape_pct": round(sum(mapes) / len(mapes), 3) if mapes else None,
        "median_mape_pct": round(sorted(mapes)[len(mapes) // 2], 3) if mapes else None,
        "best": scored[:5],
        "worst": scored[-5:][::-1] if scored else [],
        "note": "MAPE comes from a holdout backtest, not from the fit that produced the forecast.",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


@router.post("/rebuild", summary="Recompute every forecast as a background job")
def rebuild(
    session: DbSession, user: ReadUser, horizon: Annotated[int, Query(ge=1, le=60)] = 14
) -> dict[str, Any]:
    """Enqueue a full forecast run rather than blocking on it."""
    from app.jobs import queue

    handle = queue.enqueue(
        session,
        "forecast",
        {"horizon": horizon},
        requested_by=user.user_id,
        requested_by_email=user.email,
    )
    return {
        "job_id": handle.job_id,
        "job_key": handle.job_key,
        "status": handle.status,
        "href": f"/api/v1/jobs/{handle.job_key}",
    }
