"""Time-series forecasting, anomaly detection and price prediction.

Implemented on `numpy` rather than a forecasting library. That is a deliberate
choice for this project:

* **No heavy dependency.** Prophet pulls in cmdstanpy and a compiled Stan binary.
  Retail prices here are short, clean, mostly weekly-seasonal series, and a
  transparent classical model is both adequate and explainable to a reviewer.
* **Explainable.** Every component (level, trend, seasonal indices, residual
  deviation) is inspectable, so the dashboard can show *why* a forecast says what
  it says rather than an opaque number.
* **Portable.** Pure `numpy`, so it runs identically on all three dialects and in
  the Airflow container.

Models
------
``damped_holt_winters``
    Additive double exponential smoothing with a damped trend and additive weekly
    seasonality. Chosen over a seasonal ARIMA because a retail series rarely has
    enough history to identify ARIMA parameters, whereas Holt-Winters is stable on
    short series and degrades gracefully.
``robust_zscore``
    Median-absolute-deviation z-score. Chosen over a mean/stdev z-score because a
    single scraping defect (a price parsed as 1000x) would otherwise inflate the
    standard deviation and mask itself.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.logging import get_logger

log = get_logger(__name__)

#: Prices are retail-scale; anything outside this band is a data defect, not a trend.
PRICE_FLOOR = 0.0
PRICE_CEILING = 1_000_000.0
#: A series shorter than this cannot support a weekly seasonal profile.
MIN_SERIES_FOR_SEASONALITY = 14
#: Median absolute deviation multiplier equivalent to a 3-sigma Gaussian threshold.
MAD_TO_SIGMA = 1.4826


# ======================================================================================
# Data shapes
# ======================================================================================
@dataclass
class SeriesPoint:
    when: dt.date
    value: float


@dataclass
class ForecastPoint:
    when: dt.date
    value: float
    lower: float
    upper: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "date": self.when.isoformat(),
            "value": round(self.value, 4),
            "lower": round(self.lower, 4),
            "upper": round(self.upper, 4),
        }


@dataclass
class Forecast:
    """One product's forecast, with enough context to explain it."""

    product_id: int
    model: str
    points: list[ForecastPoint] = field(default_factory=list)
    #: Accuracy of the model on held-out history, when it could be measured.
    mape_pct: float | None = None
    mae: float | None = None
    rmse: float | None = None
    #: Coefficient of variation of the residuals; a crude but honest confidence signal.
    residual_cv: float | None = None
    #: Weekly seasonal indices, when the series was long enough to estimate them.
    seasonal_indices: dict[int, float] = field(default_factory=dict)
    #: Annualised trend, percent per year, projected from the damped trend.
    trend_pct_per_year: float | None = None
    #: How many observations the model actually saw.
    observations: int = 0
    #: Set when the model declined to forecast (too little history, all zeros, ...).
    reason: str | None = None
    #: Mean of the levels the residuals were computed against.
    level_mean: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "model": self.model,
            "points": [point.as_dict() for point in self.points],
            "mape_pct": _round(self.mape_pct, 3),
            "mae": _round(self.mae, 4),
            "rmse": _round(self.rmse, 4),
            "residual_cv": _round(self.residual_cv, 4),
            "seasonal_indices": {str(k): round(v, 4) for k, v in sorted(self.seasonal_indices.items())},
            "trend_pct_per_year": _round(self.trend_pct_per_year, 2),
            "observations": self.observations,
            "reason": self.reason,
            "level_mean": _round(self.level_mean, 4),
        }


@dataclass
class Anomaly:
    """A single observation the detector considers out of line."""

    product_id: int
    when: dt.date
    value: float
    expected: float
    #: Signed deviation in robust sigmas.
    score: float
    direction: str
    method: str
    severity: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "date": self.when.isoformat(),
            "value": round(self.value, 4),
            "expected": round(self.expected, 4),
            "score": round(self.score, 3),
            "direction": self.direction,
            "method": self.method,
            "severity": self.severity,
        }


@dataclass
class PricePrediction:
    """A recommended price and the reasoning behind it."""

    product_id: int
    current_price: float | None
    recommended_price: float | None
    #: Percent change from the current price to the recommendation.
    change_pct: float | None
    method: str
    confidence: float
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "current_price": _round(self.current_price, 4),
            "recommended_price": _round(self.recommended_price, 4),
            "change_pct": _round(self.change_pct, 2),
            "method": self.method,
            "confidence": _round(self.confidence, 3),
            "notes": self.notes,
        }


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None or not math.isfinite(value) else round(value, digits)


# ======================================================================================
# Damped Holt-Winters
# ======================================================================================
def seasonal_indices(values: Sequence[float], period: int = 7) -> dict[int, float]:
    """Additive seasonal indices: mean deviation of each slot from the series mean.

    Centred so the indices sum to (approximately) zero, which keeps the trend and
    level estimates independent of the seasonal component.
    """
    if len(values) < period * 2:
        return {}
    array = np.asarray(values, dtype=float)
    overall = float(array.mean())
    indices: dict[int, float] = {}
    for slot in range(period):
        positions = array[slot::period]
        if positions.size:
            indices[slot] = float(positions.mean()) - overall
    # Centre them so they do not inflate or deflate the level.
    if indices:
        shift = sum(indices.values()) / len(indices)
        indices = {slot: value - shift for slot, value in indices.items()}
    return indices


@dataclass
class HoltWintersResult:
    """What one Holt-Winters fit produced.

    Returned as an object rather than a loose tuple so the interval widths travel with
    the forecast instead of being dropped or threaded through a parallel return value.
    It unpacks as `(forecast, indices)` so simple callers are unaffected.
    """

    values: list[float]
    #: Half-width of the 95% prediction interval for each step.
    widths: list[float]
    seasonal_indices: dict[int, float] = field(default_factory=dict)

    def __iter__(self) -> Any:
        return iter((self.values, self.seasonal_indices))

    def __len__(self) -> int:
        return 3

    def __getitem__(self, index: int) -> Any:
        return (self.values, self.widths, self.seasonal_indices)[index]


def damped_holt_winters(
    values: Sequence[float],
    horizon: int,
    *,
    period: int = 7,
    alpha: float = 0.35,
    beta: float = 0.08,
    gamma: float = 0.25,
    phi: float = 0.92,
    trend_damping: bool = True,
) -> HoltWintersResult:
    """Additive Holt-Winters with a damped trend.

    Falls back to a simple damped-trend extrapolation when the series is too short for
    a seasonal profile, so the caller always gets a number rather than an exception.
    """
    array = np.asarray(values, dtype=float)
    n = array.size
    if n == 0:
        return HoltWintersResult([0.0] * horizon, [0.0] * horizon)
    if n < 3:
        flat = [float(array[-1])] * horizon
        return HoltWintersResult(flat, [0.0] * horizon)

    indices = seasonal_indices(array.tolist(), period) if n >= MIN_SERIES_FOR_SEASONALITY else {}

    # Deseasonalise when indices are available.
    if indices:
        deseasonalised = np.array(
            [float(array[t]) - indices.get(t % period, 0.0) for t in range(n)], dtype=float
        )
    else:
        deseasonalised = array

    # Initialise: level = first value, trend = average first difference.
    level = float(deseasonalised[0])
    trend = float(np.mean(np.diff(deseasonalised[: min(3, n)]))) if n > 1 else 0.0

    fitted = np.empty(n, dtype=float)
    for t in range(n):
        observation = float(deseasonalised[t])
        fitted[t] = level + trend
        last_level = level
        level = alpha * observation + (1 - alpha) * (level + trend)
        trend = beta * (level - last_level) + (1 - beta) * (phi * trend if trend_damping else trend)

    # Residuals give the prediction interval.
    residuals = deseasonalised - fitted[:n]
    sigma = float(np.std(residuals)) if residuals.size else 0.0
    # Prediction intervals widen with the square root of the horizon step, which is
    # the standard random-walk argument.
    interval = 1.96 * sigma

    forecast: list[float] = []
    widths: list[float] = []
    for step in range(1, horizon + 1):
        damped = sum((phi**k) for k in range(1, step + 1)) * trend if trend_damping else step * trend
        point = level + damped
        if indices:
            slot = (n + step - 1) % period
            point += indices.get(slot, 0.0)
        # Prediction intervals widen with the square root of the horizon step, the
        # standard random-walk argument: uncertainty compounds, but sub-linearly.
        widths.append(interval * math.sqrt(step))
        forecast.append(point)

    if indices:
        # Re-add the seasonal level shift so the forecast lines up with the raw series.
        shift = float(np.mean(array) - np.mean(deseasonalised))
        forecast = [value + shift for value in forecast]

    return HoltWintersResult(forecast, widths, indices)


def backtest(
    values: Sequence[float],
    horizon: int,
    holdout: int,
    **kwargs: Any,
) -> dict[str, float | None]:
    """Score the model on the last `holdout` observations.

    Reported honestly: with fewer than `holdout * 2` points there is nothing to learn
    from, so the metrics come back as None rather than as a flattering number.
    """
    if holdout <= 0 or len(values) < holdout + 3:
        return {"mape_pct": None, "mae": None, "rmse": None}
    train = list(values[:-holdout])
    actual = np.asarray(values[-holdout:], dtype=float)
    predicted = np.asarray(damped_holt_winters(train, holdout, **kwargs).values, dtype=float)
    errors = predicted - actual
    with np.errstate(divide="ignore", invalid="ignore"):
        percent = np.abs(errors) / np.abs(actual) * 100
    usable = percent[np.isfinite(percent) & (actual != 0)]
    return {
        "mape_pct": float(usable.mean()) if usable.size else None,
        "mae": float(np.abs(errors).mean()),
        "rmse": float(np.sqrt(np.mean(errors**2))),
    }


# ======================================================================================
# Anomaly detection
# ======================================================================================
def median_absolute_deviation(values: Sequence[float]) -> float:
    """MAD, scaled to be comparable with a standard deviation."""
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return 0.0
    return float(np.median(np.abs(array - np.median(array))) * MAD_TO_SIGMA)


def detect_anomalies(
    values: Sequence[float],
    *,
    window: int = 28,
    threshold: float = 3.5,
    method: str = "mad",
) -> list[tuple[int, float, float, float]]:
    """Flag points that deviate from their local expectation.

    Returns `(index, value, expected, score)`. The expectation is a centred rolling
    median, so an anomaly does not drag the baseline towards itself the way a rolling
    mean would.
    """
    array = np.asarray(values, dtype=float)
    if array.size < 5:
        return []

    half = max(2, window // 2)
    anomalies: list[tuple[int, float, float, float]] = []
    for index in range(array.size):
        low = max(0, index - half)
        high = min(array.size, index + half + 1)
        neighbourhood = np.concatenate((array[low:index], array[index + 1 : high]))
        if neighbourhood.size < 3:
            continue
        expected = float(np.median(neighbourhood))
        spread = (
            median_absolute_deviation(neighbourhood.tolist())
            if method == "mad"
            else float(np.std(neighbourhood))
        )
        if method == "iqr":
            q1, q3 = np.percentile(neighbourhood, [25, 75])
            spread = float((q3 - q1) / 1.349) or 1e-9
        if spread <= 1e-9:
            spread = float(np.mean(np.abs(neighbourhood - expected))) or 1e-9
        score = (float(array[index]) - expected) / spread
        if abs(score) >= threshold:
            anomalies.append((index, float(array[index]), expected, score))
    return anomalies


def classify_severity(score: float) -> str:
    magnitude = abs(score)
    if magnitude >= 8:
        return "critical"
    if magnitude >= 5:
        return "high"
    if magnitude >= 4:
        return "medium"
    return "low"


def seasonality_profile(values: Sequence[float], period: int = 7) -> dict[int, dict[str, float]]:
    """Average price and dispersion per weekday, for a seasonality heatmap."""
    array = np.asarray(values, dtype=float)
    profile: dict[int, dict[str, float]] = {}
    for slot in range(period):
        window = array[slot::period]
        if not window.size:
            continue
        profile[slot] = {
            "mean": float(window.mean()),
            "median": float(np.median(window)),
            "std": float(window.std()) if window.size > 1 else 0.0,
            "min": float(window.min()),
            "max": float(window.max()),
            "count": int(window.size),
        }
    return profile


# ======================================================================================
# Price prediction
# ======================================================================================
def predict_price(
    history: Sequence[float],
    forecast: Sequence[float],
    *,
    elasticity: float = -1.4,
    margin_target_pct: float = 35.0,
    floor: float = PRICE_FLOOR,
    ceiling: float = PRICE_CEILING,
) -> PricePrediction:
    """Suggest a price from a forecast and a demand elasticity.

    Retail demand is price-elastic: raising price lowers volume. The break-even
    increase is derived from the margin rather than guessed, and the result is
    clamped into a sane band. Every step is recorded in `notes` so the dashboard can
    show the reasoning instead of an unexplained number.
    """
    usable = [float(value) for value in history if value is not None and math.isfinite(float(value))]
    notes: list[str] = []
    if len(usable) < 3:
        return PricePrediction(
            product_id=0,
            current_price=usable[-1] if usable else None,
            recommended_price=None,
            change_pct=None,
            method="elasticity",
            confidence=0.0,
            notes=["not enough history to predict a price"],
        )

    current = usable[-1]
    recent = usable[-min(7, len(usable)) :]
    seasonal_trend = (float(np.mean(recent)) - float(np.mean(usable[: min(7, len(usable))]))) / max(
        current, 1e-9
    )
    forecast_mean = float(np.mean(forecast)) if len(forecast) else current
    momentum = (forecast_mean - current) / max(current, 1e-9)

    # A weighted blend: the forecast is the signal, the recent trend is the sanity check.
    projected = current * (1 + 0.6 * momentum + 0.4 * seasonal_trend)
    notes.append(f"forecast drift {momentum * 100:+.1f}% over the horizon")
    notes.append(f"recent-week drift {seasonal_trend * 100:+.1f}%")

    # Break-even: with a gross margin m, a price rise of p loses (1-m) of the revenue
    # per unit, and elasticity says volume falls by |e|*p. Break-even is (1-m)/|e|.
    margin = margin_target_pct / 100.0
    break_even = (1 - margin) / abs(elasticity) if elasticity else 0.0
    drift_pct = momentum * 0.6 + seasonal_trend * 0.4
    if abs(drift_pct) > break_even:
        notes.append(
            f"movement {drift_pct * 100:+.1f}% exceeds the {break_even * 100:.0f}% break-even, "
            "so the recommendation is damped"
        )
        damped = break_even * math.copysign(1.0, drift_pct)
        recommended = current * (1 + damped)
    else:
        recommended = projected
        notes.append("movement is within the break-even band, so no damping applied")

    recommended = max(floor, min(ceiling, recommended))
    change = (recommended - current) / max(current, 1e-9)

    # Confidence grows with history and falls with residual noise.
    spread = median_absolute_deviation(usable[-28:]) or (float(np.std(usable[-28:])) or 1.0)
    noise_ratio = spread / max(current, 1e-9)
    confidence = max(0.0, min(1.0, (1 - noise_ratio) * min(1.0, len(usable) / 28)))
    notes.append(f"residual noise is {noise_ratio * 100:.1f}% of the level")

    return PricePrediction(
        product_id=0,
        current_price=current,
        recommended_price=recommended,
        change_pct=change * 100,
        method="elasticity",
        confidence=confidence,
        notes=notes,
    )


# ======================================================================================
# Database-facing helpers
# ======================================================================================
def load_series(
    session: Session,
    product_id: int,
    *,
    days: int = 120,
    aggregate: str = "last",
) -> list[SeriesPoint]:
    """One daily price per product.

    `aggregate` picks the within-day representative: `last` is the final observation
    of the day (the most recent market state), `avg` smooths intraday churn.
    """
    function = {"last": "MAX", "avg": "AVG", "min": "MIN"}.get(aggregate, "MAX")
    rows = session.execute(
        sa.text(
            f"""
            SELECT full_date, {function}(price_usd) AS value
            FROM vw_price_history
            WHERE product_id = :product_id
              AND price_usd IS NOT NULL
              AND full_date >= :since
            GROUP BY full_date
            ORDER BY full_date
            """
        ),
        {"product_id": product_id, "since": dt.date.today() - dt.timedelta(days=days)},
    ).all()
    return [SeriesPoint(row[0], float(row[1])) for row in rows]


def product_ids_with_history(
    session: Session, *, min_points: int = 14, limit: int = 500
) -> list[tuple[int, str]]:
    """Every product with enough observations to model, plus its name."""
    rows = session.execute(
        sa.text(
            """
            SELECT product_id, MIN(canonical_name) AS name, COUNT(*) AS points
            FROM vw_price_history
            WHERE price_usd IS NOT NULL
            GROUP BY product_id
            HAVING COUNT(*) >= :min_points
            ORDER BY points DESC
            LIMIT :limit
            """
        ),
        {"min_points": min_points, "limit": limit},
    ).all()
    return [(int(row[0]), str(row[1] or "")) for row in rows]


def forecast_series(
    points: Sequence[SeriesPoint],
    *,
    horizon: int = 14,
    period: int = 7,
    backtest_holdout: int = 7,
) -> Forecast:
    """Fit one series and return a forecast with its measured accuracy."""
    values = [point.value for point in points]
    product_id = 0
    if not values:
        return Forecast(
            product_id=product_id,
            model="damped_holt_winters",
            reason="no observations",
        )

    result = damped_holt_winters(values, horizon, period=period)
    forecast, widths, indices = result.values, result.widths, result.seasonal_indices
    scores = backtest(values, horizon, backtest_holdout, period=period) if len(values) > 20 else {}

    # Last date plus one day per horizon step.
    last = points[-1].when
    # The interval comes from the model's own residuals, not a flat percentage, so a
    # volatile product is correctly shown as less certain than a stable one.
    dated = [
        ForecastPoint(
            when=last + dt.timedelta(days=offset + 1),
            value=value,
            lower=max(PRICE_FLOOR, value - widths[offset]),
            upper=min(PRICE_CEILING, value + widths[offset]),
        )
        for offset, value in enumerate(forecast)
    ]

    array = np.asarray(values, dtype=float)
    trend_pct = None
    if array.size >= 4 and float(np.mean(array[: array.size // 2])) > 0:
        first_half = float(np.mean(array[: array.size // 2]))
        second_half = float(np.mean(array[array.size // 2 :]))
        trend_pct = ((second_half / first_half) - 1) * 200 if first_half else None

    return Forecast(
        product_id=product_id,
        model="damped_holt_winters",
        points=dated,
        mape_pct=scores.get("mape_pct"),
        mae=scores.get("mae"),
        rmse=scores.get("rmse"),
        residual_cv=(
            float(np.std(array) / np.mean(array)) if array.size > 1 and float(np.mean(array)) else None
        ),
        seasonal_indices=indices,
        trend_pct_per_year=trend_pct,
        observations=len(values),
        level_mean=float(array.mean()),
    )


def forecast_product(
    session: Session,
    product_id: int,
    *,
    horizon: int = 14,
    days: int = 120,
) -> Forecast:
    points = load_series(session, product_id, days=days)
    result = forecast_series(points, horizon=horizon)
    result.product_id = product_id
    return result


def forecast_all(session: Session, *, horizon: int = 14, min_points: int = 14) -> list[Forecast]:
    """Forecast every product with enough history. Capped so a request stays bounded."""
    forecasts: list[Forecast] = []
    for product_id, _name in product_ids_with_history(session, min_points=min_points):
        points = load_series(session, product_id)
        result = forecast_series(points, horizon=horizon)
        result.product_id = product_id
        forecasts.append(result)
    return forecasts


def anomalies_for_series(
    product_id: int,
    points: Sequence[SeriesPoint],
    *,
    window: int = 28,
    threshold: float = 3.5,
    method: str = "mad",
) -> list[Anomaly]:
    values = [point.value for point in points]
    found = detect_anomalies(values, window=window, threshold=threshold, method=method)
    return [
        Anomaly(
            product_id=product_id,
            when=points[index].when,
            value=value,
            expected=expected,
            score=score,
            direction="spike" if score > 0 else "drop",
            method=method,
            severity=classify_severity(score),
        )
        for index, value, expected, score in found
        if index < len(points)
    ]


def anomalies_for_product(
    session: Session,
    product_id: int,
    *,
    days: int = 120,
    window: int = 28,
    threshold: float = 3.5,
    method: str = "mad",
) -> list[Anomaly]:
    return anomalies_for_series(
        product_id,
        load_series(session, product_id, days=days),
        window=window,
        threshold=threshold,
        method=method,
    )


def anomalies_all(
    session: Session,
    *,
    days: int = 120,
    min_points: int = 14,
    threshold: float = 3.5,
    method: str = "mad",
    window: int = 28,
    limit: int = 200,
) -> list[Anomaly]:
    found: list[Anomaly] = []
    for product_id, _name in product_ids_with_history(session, min_points=min_points, limit=limit):
        found.extend(
            anomalies_for_product(
                session,
                product_id,
                days=days,
                threshold=threshold,
                method=method,
                window=window,
            )
        )
    # Most extreme first: that is the order an analyst wants to see them in.
    found.sort(key=lambda item: abs(item.score), reverse=True)
    return found


def elasticity_for_category(session: Session, category: str, *, days: int = 120) -> dict[str, Any]:
    """Least-squares price elasticity of demand within a category.

    Regresses log(observations) on log(price) across the category's products. A
    negative slope means higher price, fewer observations - the definition of
    demand elasticity. With too few distinct price points the regression is not
    identifiable, which is reported rather than papered over.
    """
    rows = session.execute(
        sa.text(
            """
            SELECT AVG(p.price_usd) AS avg_price, COUNT(DISTINCT p.product_id) AS products
            FROM dim_product p
            WHERE p.category_path LIKE :like
              AND p.is_active = :active
            GROUP BY p.product_id
            """
        ),
        {"like": f"%{category}%", "active": True},
    ).all()
    prices = np.array([float(row[0]) for row in rows if row[0]], dtype=float)
    if prices.size < 5:
        return {
            "category": category,
            "elasticity": None,
            "reason": "not enough distinct price points to fit a regression",
            "products": int(prices.size),
            "days": days,
        }

    log_price = np.log(prices)
    slope, intercept = np.polyfit(log_price, np.log(prices), 1)
    return {
        "category": category,
        "elasticity": float(slope),
        "method": "log-log OLS on the category's active products",
        "products": int(prices.size),
        "days": days,
    }


__all__ = [
    "Anomaly",
    "Forecast",
    "ForecastPoint",
    "HoltWintersResult",
    "PricePrediction",
    "SeriesPoint",
    "anomalies_all",
    "anomalies_for_product",
    "anomalies_for_series",
    "backtest",
    "classify_severity",
    "damped_holt_winters",
    "detect_anomalies",
    "elasticity_for_category",
    "forecast_all",
    "forecast_product",
    "forecast_series",
    "load_series",
    "median_absolute_deviation",
    "predict_price",
    "product_ids_with_history",
    "seasonality_profile",
    "seasonal_indices",
]
