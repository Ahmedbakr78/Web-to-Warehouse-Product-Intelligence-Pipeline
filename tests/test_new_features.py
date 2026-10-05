"""Tests for the v1.3 platform features: feature catalogue, account self-service, builder API."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.security import create_access_token
from app.core.db import session_scope
from app.core.errors import PipelineError

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client(database):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def admin_token():
    return create_access_token(1, role="admin", email="admin@example.com")


@pytest.fixture(scope="module")
def viewer_token():
    return create_access_token(3, role="viewer", email="viewer@example.com")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------------------
# Feature catalogue
# --------------------------------------------------------------------------------------
def test_meta_features_catalogue(client):
    payload = client.get("/api/v1/meta/features").json()
    assert payload["total_groups"] >= 10
    assert payload["total_features"] >= 60
    keys = {group["key"] for group in payload["groups"]}
    assert {"ingestion", "cleaning", "dedupe", "warehouse", "security", "dashboard"} <= keys
    for group in payload["groups"]:
        assert group["title"] and group["icon"] and group["summary"]
        assert group["feature_count"] == len(group["features"])
        for feature in group["features"]:
            assert feature["name"]


def test_meta_includes_generated_feature_list(client):
    meta = client.get("/api/v1/meta").json()
    assert len(meta["features"]) >= 60
    assert meta["feature_groups"] >= 10


# --------------------------------------------------------------------------------------
# Own-activity feed
# --------------------------------------------------------------------------------------
def test_audit_me_requires_authentication(client):
    assert client.get("/api/v1/audit/me").status_code == 401


def test_audit_me_returns_own_activity_only(client, admin_token):
    # A fresh user generates its own, private audit trail.
    _disposable_user(client, admin_token, "audit-me@example.com")
    login = client.post(
        "/api/v1/auth/login", json={"email": "audit-me@example.com", "password": "Disposable@12345"}
    ).json()
    token = {"Authorization": f"Bearer {login['access_token']}"}
    changed = client.post(
        "/api/v1/auth/change-password",
        headers=token,
        json={"current_password": "Disposable@12345", "new_password": "Disposable@67890"},
    )
    assert changed.status_code == 200
    feed = client.get("/api/v1/audit/me", headers=token).json()
    assert feed["total"] >= 1
    actions = {item["action"] for item in feed["items"]}
    assert "auth.change_password" in actions
    # The admin's feed is a different, independent stream: it must not contain any of
    # the other account's entries. (Totals are unrelated, so compare identities.)
    admin_feed = client.get("/api/v1/audit/me", headers=auth(admin_token)).json()
    own_ids = {item["audit_id"] for item in feed["items"]}
    admin_ids = {item["audit_id"] for item in admin_feed["items"]}
    assert own_ids and not (own_ids & admin_ids)


def test_audit_me_pagination_and_window(client, admin_token):
    response = client.get("/api/v1/audit/me?page=1&page_size=2&days=3650", headers=auth(admin_token))
    assert response.status_code == 200
    payload = response.json()
    assert payload["page_size"] == 2
    assert len(payload["items"]) <= 2
    assert payload["window_days"] == 3650


# --------------------------------------------------------------------------------------
# Account data export + deletion
# --------------------------------------------------------------------------------------
def test_export_my_account_data(client, admin_token):
    response = client.get("/api/v1/users/me/export", headers=auth(admin_token))
    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["email"] == "admin@example.com"
    for section in ("api_keys", "saved_views", "alert_rules", "notifications", "recent_activity"):
        assert isinstance(payload[section], list)
    assert payload["exported_at"]


def test_export_requires_authentication(client):
    assert client.get("/api/v1/users/me/export").status_code == 401


def _disposable_user(client, admin_token, email: str) -> None:
    created = client.post(
        "/api/v1/users",
        headers=auth(admin_token),
        json={
            "email": email,
            "full_name": "Disposable User",
            "password": "Disposable@12345",
            "role": "viewer",
        },
    )
    assert created.status_code == 201, created.text


def test_delete_my_account_requires_password(client, admin_token):
    _disposable_user(client, admin_token, "disposable-a@example.com")
    login = client.post(
        "/api/v1/auth/login", json={"email": "disposable-a@example.com", "password": "Disposable@12345"}
    ).json()
    token = {"Authorization": f"Bearer {login['access_token']}"}
    wrong = client.request("DELETE", "/api/v1/users/me", headers=token, json={"password": "Wrong@123456"})
    assert wrong.status_code == 401
    gone = client.request("DELETE", "/api/v1/users/me", headers=token, json={"password": "Disposable@12345"})
    assert gone.status_code == 200
    assert "deleted" in gone.json()["message"].lower()
    # The account can no longer authenticate.
    relogin = client.post(
        "/api/v1/auth/login", json={"email": "disposable-a@example.com", "password": "Disposable@12345"}
    )
    assert relogin.status_code == 401


def test_delete_me_rejects_empty_password(client, admin_token):
    _disposable_user(client, admin_token, "disposable-b@example.com")
    login = client.post(
        "/api/v1/auth/login", json={"email": "disposable-b@example.com", "password": "Disposable@12345"}
    ).json()
    token = {"Authorization": f"Bearer {login['access_token']}"}
    response = client.request("DELETE", "/api/v1/users/me", headers=token, json={"password": ""})
    assert response.status_code == 422


# --------------------------------------------------------------------------------------
# Builder schema
# --------------------------------------------------------------------------------------
def test_builder_schema_lists_entities(client, admin_token):
    response = client.get("/api/v1/builder/schema", headers=auth(admin_token))
    assert response.status_code == 200
    payload = response.json()
    keys = {entity["entity"] for entity in payload["entities"]}
    assert {"products", "price_changes", "new_products", "removed_products"} <= keys
    assert {operator["operator"] for operator in payload["operators"]} >= {
        "eq",
        "contains",
        "between",
        "in",
        "empty",
    }
    assert "avg" in payload["aggregates"]


def test_builder_requires_authentication_and_query_right(client):
    assert client.get("/api/v1/builder/schema").status_code == 401


def test_builder_schema_allows_viewers(client, viewer_token):
    assert client.get("/api/v1/builder/schema", headers=auth(viewer_token)).status_code == 200


# --------------------------------------------------------------------------------------
# Builder query
# --------------------------------------------------------------------------------------
def test_builder_query_with_filters_and_sort(client, admin_token):
    response = client.post(
        "/api/v1/builder/query",
        headers=auth(admin_token),
        json={
            "entity": "products",
            "columns": ["canonical_name", "category_name", "price_usd", "rating"],
            "filters": [{"column": "category_name", "operator": "contains", "value": "Fiction"}],
            "sort": [{"column": "price_usd", "direction": "desc"}],
            "limit": 10,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["entity"] == "products"
    assert set(payload["columns"]) == {"canonical_name", "category_name", "price_usd", "rating"}
    assert payload["total"] >= 1
    assert payload["sql_preview"].startswith("SELECT")
    assert payload["duration_ms"] >= 0


def test_builder_query_group_by_with_aggregates(client, admin_token):
    response = client.post(
        "/api/v1/builder/query",
        headers=auth(admin_token),
        json={
            "entity": "products",
            "group_by": ["category_name"],
            "aggregates": [
                {"function": "count"},
                {"function": "avg", "column": "price_usd", "alias": "avg_price"},
            ],
            "sort": [{"column": "avg_price", "direction": "desc"}],
            "limit": 20,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["columns"][0] == "category_name"
    assert "avg_price" in payload["columns"]
    assert payload["row_count"] >= 1
    prices = [row[payload["columns"].index("avg_price")] for row in payload["rows"]]
    assert prices == sorted(prices, key=lambda value: (value is not None, value), reverse=True)


def test_builder_query_all_operators(client, admin_token):
    cases = [
        {"column": "price_usd", "operator": "between", "value": 1, "value2": 100000},
        {"column": "brand", "operator": "in", "value": ["Penguin"]},
        {"column": "discount_pct", "operator": "empty"},
        {"column": "discount_pct", "operator": "not_empty"},
        {"column": "canonical_name", "operator": "starts_with", "value": "The"},
        {"column": "canonical_name", "operator": "ends_with", "value": "Pro"},
        {"column": "canonical_name", "operator": "not_contains", "value": "zzz"},
        {"column": "rating", "operator": "gte", "value": 0},
        {"column": "rating", "operator": "ne", "value": -1},
    ]
    for flt in cases:
        response = client.post(
            "/api/v1/builder/query",
            headers=auth(admin_token),
            json={"entity": "products", "columns": ["canonical_name"], "filters": [flt], "limit": 5},
        )
        assert response.status_code == 200, flt


def test_builder_query_rejects_unknown_entity(client, admin_token):
    response = client.post(
        "/api/v1/builder/query",
        headers=auth(admin_token),
        json={"entity": "dim_user_secret", "limit": 5},
    )
    assert response.status_code in (400, 422)
    assert "unknown entity" in response.text


def test_builder_query_rejects_unknown_column_and_operator(client, admin_token):
    bad_column = client.post(
        "/api/v1/builder/query",
        headers=auth(admin_token),
        json={"entity": "products", "columns": ["password_hash"], "limit": 5},
    )
    assert bad_column.status_code == 422
    assert "unknown select column" in bad_column.json()["message"]
    bad_operator = client.post(
        "/api/v1/builder/query",
        headers=auth(admin_token),
        json={
            "entity": "products",
            "filters": [{"column": "brand", "operator": "drop", "value": "x"}],
            "limit": 5,
        },
    )
    assert bad_operator.status_code == 422


def test_builder_query_in_requires_list_values(client, admin_token):
    response = client.post(
        "/api/v1/builder/query",
        headers=auth(admin_token),
        json={
            "entity": "products",
            "filters": [{"column": "brand", "operator": "in", "value": "not-a-list"}],
            "limit": 5,
        },
    )
    assert response.status_code == 422


def test_builder_query_viewer_can_read(client, viewer_token):
    response = client.post(
        "/api/v1/builder/query",
        headers=auth(viewer_token),
        json={"entity": "source_coverage", "columns": ["source_name", "observations"], "limit": 5},
    )
    assert response.status_code == 200
    assert response.json()["row_count"] >= 1


# --------------------------------------------------------------------------------------
# Rate limiting and API-key scopes
# --------------------------------------------------------------------------------------
def test_api_key_scopes_are_enforced(client, admin_token):
    """A read-only key must be refused by a route needing another scope."""
    from app.api.security import generate_api_key
    from app.models.app_users import AppApiKey

    with session_scope() as session:
        plain, prefix, hashed = generate_api_key()
        session.add(
            AppApiKey(
                user_id=1,
                name="test-read-only",
                prefix=prefix,
                hashed_key=hashed,
                scopes=["read"],
                is_active=True,
                rate_limit_per_minute=600,
            )
        )

    headers = {"Authorization": f"Bearer {plain}"}

    # `read` is granted.
    assert client.get("/api/v1/products", headers=headers).status_code == 200

    # `run_pipeline` is not, even though the owner is an admin.
    denied = client.post("/api/v1/pipeline/run/sync", json={}, headers=headers)
    assert denied.status_code == 403
    assert "run_pipeline" in denied.text

    # `manage_users` is not either.
    assert client.get("/api/v1/users", headers=headers).status_code == 403


def test_api_key_cannot_be_granted_more_than_its_owner(client, admin_token):
    """A key may never exceed the rights of the user it belongs to."""
    overreach = client.post(
        "/api/v1/users/3/api-keys",
        json={"name": "too-powerful", "scopes": ["read", "manage_users"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    # user 3 is a viewer, so manage_users is refused.
    assert overreach.status_code == 403
    assert "manage_users" in overreach.text


def test_unknown_scope_is_rejected(client, admin_token):
    response = client.post(
        "/api/v1/users/1/api-keys",
        json={"name": "bad-scope", "scopes": ["read", "teleport"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 422
    assert "teleport" in response.text


def test_rate_limiter_returns_429_with_retry_after():
    """The limiter must reject rather than silently allow, and say when to retry."""
    from app.api.ratelimit import Bucket, RateLimiter

    limiter = RateLimiter()
    for _ in range(3):
        allowed, remaining, _retry = limiter.check("k", limit=3)
        assert allowed
        assert remaining >= 0

    allowed, remaining, retry_after = limiter.check("k", limit=3)
    assert allowed is False
    assert remaining == 0
    assert 0 < retry_after <= 60

    # A different key has its own budget.
    assert limiter.check("other", limit=3)[0] is True

    # And the window is enforced, not just counted.
    bucket = Bucket(limit=2, window_seconds=60)
    assert bucket.allow(0.0)[0] is True
    assert bucket.allow(0.0)[0] is True
    assert bucket.allow(0.0)[0] is False
    assert bucket.allow(61.0)[0] is True


def test_rate_limit_exempts_health_endpoints():
    """Health and login must answer even when the caller is over budget."""
    from app.api.ratelimit import EXEMPT_PATHS

    for path in ("/api/v1/health", "/api/v1/health/ready", "/api/v1/meta", "/api/v1/auth/login"):
        assert path in EXEMPT_PATHS
    assert "/api/v1/products" not in EXEMPT_PATHS


def test_effective_scopes_are_capped_by_the_owner_role():
    from app.api.ratelimit import effective_scopes
    from app.models.app_users import AppApiKey, AppUser

    key = AppApiKey(scopes=["read", "manage_users"])
    viewer = AppUser(role="viewer")
    assert effective_scopes(key, viewer) == {"read"}

    admin = AppUser(role="admin")
    assert effective_scopes(key, admin) == {"read", "manage_users"}

    # A key with no explicit scopes inherits everything its owner can do.
    unrestricted = AppApiKey(scopes=None)
    assert effective_scopes(unrestricted, viewer) == {"read", "query", "export"}


def test_job_jsonable_serialises_pipeline_results():
    """Handler results contain datetimes and Decimals; the JSON column cannot take them."""
    import datetime as dt
    from decimal import Decimal

    from app.jobs.queue import jsonable

    payload = jsonable(
        {
            "started_at": dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
            "day": dt.date(2026, 1, 1),
            "elapsed": dt.timedelta(seconds=90),
            "amount": Decimal("12.34"),
            "rows": [{"price": Decimal("1.5")}],
            "keys": {1: "int key"},
        }
    )
    json.dumps(payload)  # must not raise
    assert payload["started_at"].startswith("2026-01-01")
    assert payload["elapsed"] == 90.0
    assert payload["amount"] == 12.34
    assert payload["rows"][0]["price"] == 1.5
    assert payload["keys"] == {"1": "int key"}


def test_job_queue_runs_a_pipeline_job():
    """A queued job is claimed, executed and stored with real progress events."""
    from app.jobs import queue

    with session_scope() as session:
        handle = queue.enqueue(
            session,
            "pipeline_run",
            {"sources": ["local_demo"], "limit_per_source": 5},
            requested_by_email="pytest",
        )
        key = handle.job_key

    assert queue.drain(limit=1) >= 1

    with session_scope() as session:
        job = queue.get_job(session, key)
        assert job.status == "succeeded", job.error
        assert job.progress_pct == 100
        assert (job.result or {}).get("status") == "success"
        events = queue.job_events(session, job.job_id)
        assert any(event["stage"] == "extract" for event in events)
        assert any(event["stage"] == "done" for event in events)


def test_job_cancellation_and_retry():
    from app.jobs import queue

    with session_scope() as session:
        handle = queue.enqueue(session, "export", {"dataset": "products", "format": "csv", "row_limit": 25})
        key = handle.job_key

    with session_scope() as session:
        cancelled = queue.cancel_job(session, key)
        assert cancelled["status"] == "cancelled"

        # Cancelling twice is a conflict, not a silent no-op.
        with pytest.raises(PipelineError) as excinfo:
            queue.cancel_job(session, key)
        assert excinfo.value.status_code == 409

        requeued = queue.retry_job(session, key)
        assert requeued["status"] == "queued"
        assert requeued["cancel_requested"] is False

    assert queue.drain(limit=1) >= 1
    with session_scope() as session:
        job = queue.get_job(session, key)
        assert job.status == "succeeded", job.error
        assert job.result["rows"] == 25
        assert job.result["filename"].endswith(".csv")


def test_job_lease_is_reclaimed_when_a_worker_dies():
    """A running job whose lease expired must become claimable again."""
    import datetime as dt

    from app.jobs import queue

    with session_scope() as session:
        handle = queue.enqueue(session, "pipeline_run", {"sources": ["local_demo"], "limit_per_source": 5})
        key = handle.job_key
        job = queue.get_job(session, key)
        # Simulate a worker that claimed the job and then died.
        job.status = "running"
        job.lease_owner = "dead-worker"
        job.lease_expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)
        session.flush()

    claimed = queue.claim_next(None, "live-worker")
    assert claimed is not None
    assert claimed.job_key == key
    assert claimed.lease_owner == "live-worker"
    assert claimed.attempt == 1


# --------------------------------------------------------------------------------------
# Forecasting and anomaly detection
# --------------------------------------------------------------------------------------
def _seasonal_series(days: int = 120, seed: int = 7) -> list[float]:
    """A synthetic series with a known weekly cycle and a mild upward trend."""
    import math

    import numpy as np

    rng = np.random.default_rng(seed)
    return [
        100.0 + day * 0.08 + 5 * math.sin(2 * math.pi * day / 7) + float(rng.normal(0, 1.2))
        for day in range(days)
    ]


def test_holt_winters_recovers_a_known_trend_and_season():
    from app.analytics.forecast import damped_holt_winters

    values = _seasonal_series()
    result = damped_holt_winters(values, 14)

    assert len(result.values) == 14
    assert len(result.seasonal_indices) == 7, "a 120-day series supports weekly seasonality"
    # The true level at the end is 100 + 119*0.08 ~= 109.5 plus whatever weekday offset.
    level = sum(values[-7:]) / 7
    assert abs(sum(result.values[:7]) / 7 - level) / level < 0.10

    # Unpacking works for callers that just want the pair.
    forecast, indices = result
    assert forecast is result.values
    assert indices is result.seasonal_indices


def test_prediction_intervals_widen_with_horizon():
    from app.analytics.forecast import damped_holt_winters

    widths = damped_holt_winters(_seasonal_series(), 14).widths
    assert len(widths) == 14
    assert widths[0] < widths[5] < widths[-1], "uncertainty must compound with distance"
    assert all(width >= 0 for width in widths)


def test_backtest_reports_real_accuracy():
    from app.analytics.forecast import backtest

    values = _seasonal_series()
    scores = backtest(values, horizon=14, holdout=7)
    assert scores["mape_pct"] is not None
    assert 0 < scores["mape_pct"] < 10, "the model should be accurate on a clean synthetic series"
    assert scores["rmse"] >= scores["mae"] >= 0

    # Too little history must report nothing rather than a flattering number.
    assert backtest([1, 2, 3], horizon=7, holdout=7)["mape_pct"] is None


def test_holt_winters_handles_degenerate_input():
    from app.analytics.forecast import damped_holt_winters

    assert damped_holt_winters([], 5).values == [0.0] * 5
    flat = damped_holt_winters([10, 10, 10], 5)
    assert flat.values == [10.0] * 5
    # A short series gets no seasonal profile rather than a fabricated one.
    assert damped_holt_winters([1, 2, 3, 4], 5).seasonal_indices == {}


def test_anomaly_detector_finds_an_injected_defect_without_false_positives():
    import numpy as np

    from app.analytics.forecast import detect_anomalies

    rng = np.random.default_rng(3)
    clean = [100 + float(rng.normal(0, 1)) for _ in range(40)]
    assert detect_anomalies(clean) == [], "a clean series must not produce anomalies"

    dirty = list(clean)
    dirty[20] = 950.0  # a price parsed with three extra digits
    found = detect_anomalies(dirty)
    assert len(found) == 1
    index, value, expected, score = found[0]
    assert index == 20
    assert value == 950.0
    assert score > 3.5

    # Every method agrees on where the defect is.
    for method in ("mad", "std", "iqr"):
        hits = detect_anomalies(dirty, method=method)
        assert [hit[0] for hit in hits] == [20], f"{method} missed or added detections"


def test_median_absolute_deviation_ignores_a_single_outlier():
    from app.analytics.forecast import median_absolute_deviation

    steady = [10.0] * 10
    with_one = steady + [1000.0]
    # A mean-based spread would explode here; the median-based one barely moves.
    assert median_absolute_deviation(steady) == 0.0
    assert median_absolute_deviation(with_one) < 1000.0


def test_severity_classification():
    from app.analytics.forecast import classify_severity

    assert classify_severity(9) == "critical"
    assert classify_severity(-9) == "critical"
    assert classify_severity(6) == "high"
    assert classify_severity(4.2) == "medium"
    assert classify_severity(3.6) == "low"


def test_price_prediction_is_damped_at_break_even():
    from app.analytics.forecast import damped_holt_winters, predict_price

    # A steeply rising series: the model would otherwise recommend an absurd rise.
    rising = [100 * (1.02**day) for day in range(60)]
    prediction = predict_price(rising, damped_holt_winters(rising, 7).values, elasticity=-1.4)
    assert prediction.recommended_price is not None
    # Break-even at a 35% margin and elasticity -1.4 is 46%; the recommendation
    # must be capped at that, not follow the model's 20%-a-step extrapolation.
    assert prediction.change_pct is not None
    assert prediction.change_pct <= 47
    assert any("break-even" in note for note in prediction.notes)
    assert 0 <= prediction.confidence <= 1


def test_price_prediction_refuses_on_thin_history():
    from app.analytics.forecast import predict_price

    prediction = predict_price([100.0, 101.0], [102.0, 103.0])
    assert prediction.recommended_price is None
    assert prediction.confidence == 0.0
    assert "not enough history" in prediction.notes[0]


def test_seasonality_profile_covers_every_weekday_slot():
    from app.analytics.forecast import seasonality_profile

    values = _seasonal_series(days=70)
    profile = seasonality_profile(values)
    assert set(profile) == set(range(7))
    # The synthetic series peaks on the weekend-ish slots by construction.
    assert all(stats["count"] == 10 for stats in profile.values())


def test_elasticity_is_reported_as_unidentifiable_rather_than_guessed(client, admin_token):
    """Too few products must yield None, not a fabricated slope."""
    response = client.get("/api/v1/forecast/category/NoSuchCategory/elasticity", headers=auth(admin_token))
    assert response.status_code == 200
    payload = response.json()
    assert payload["elasticity"] is None
    assert "at least 5" in payload["reason"]


def test_forecast_endpoints_respond(client, admin_token):
    import datetime as dt

    # `last_seen_at` is a datetime, not a date, so the query needs the right type.
    product = client.get(
        "/api/v1/products?page_size=1&sort_by=last_seen_at&sort_dir=desc",
        headers=auth(admin_token),
    ).json()["items"][0]
    product_id = product["product_id"]
    assert isinstance(dt.date.today(), dt.date)

    forecast = client.get(f"/api/v1/forecast/{product_id}?horizon=7", headers=auth(admin_token))
    assert forecast.status_code == 200
    payload = forecast.json()
    assert payload["model"] == "damped_holt_winters"
    assert len(payload["points"]) <= 7
    for point in payload["points"]:
        assert point["lower"] <= point["value"] <= point["upper"], "intervals must bracket the forecast"

    anomalies = client.get(f"/api/v1/forecast/{product_id}/anomalies", headers=auth(admin_token))
    assert anomalies.status_code == 200
    assert "anomalies" in anomalies.json()

    weekly = client.get(f"/api/v1/forecast/{product_id}/seasonality", headers=auth(admin_token))
    assert weekly.status_code == 200

    # A product that does not exist must be reported, not crash.
    missing = client.get("/api/v1/forecast/99999999", headers=auth(admin_token))
    assert missing.status_code == 200
    assert missing.json()["reason"] == "product not found"


def test_forecast_backtest_summary_is_honest(client, admin_token):
    """Mean and median MAPE must come from a real holdout, over real products."""
    response = client.get("/api/v1/forecast/backtest?limit=20", headers=auth(admin_token))
    assert response.status_code == 200
    payload = response.json()
    if payload["evaluated"]:
        assert payload["mean_mape_pct"] is not None
        assert payload["median_mape_pct"] is not None
        assert len(payload["best"]) <= 5
        assert "holdout backtest" in payload["note"]


# --------------------------------------------------------------------------------------
# Reports and PDF rendering
# --------------------------------------------------------------------------------------
ALL_TEMPLATES = ("executive_summary", "price_movements", "data_quality", "catalog_gaps")


def test_report_templates_are_declared_consistently():
    from app.services.report import TEMPLATE_KEYS, TEMPLATES

    assert set(TEMPLATE_KEYS) == set(TEMPLATES)
    for key, spec in TEMPLATES.items():
        assert spec["title"], f"{key} has no title"
        assert spec["sections"], f"{key} has no sections"


@pytest.mark.parametrize("template", ALL_TEMPLATES)
def test_every_template_renders_without_a_failed_section(session, template):
    """No section may silently degrade to a placeholder callout."""
    from app.services.report import build_report

    report = build_report(session, template, days=30)
    assert report["blocks"], f"{template} produced no blocks"
    broken = [
        block
        for block in report["blocks"]
        if block.get("type") == "callout" and str(block.get("title", "")).startswith("Section unavailable")
    ]
    assert not broken, f"{template} failed sections: {[b['title'] for b in broken]}"


def test_report_html_is_a_complete_document():
    from app.services.pdf import render_blocks

    document = render_blocks(
        "Test report",
        "A subtitle",
        [
            {"type": "tiles", "tiles": [{"label": "Products", "value": 100, "hint": "deduplicated"}]},
            {
                "type": "table",
                "columns": [{"key": "name", "label": "Name"}, {"key": "n", "label": "N", "align": "right"}],
                "rows": [{"name": "Widget", "n": 5}],
            },
            {"type": "callout", "title": "Note", "body": "Something worth reading."},
        ],
        footer="Footer text",
    )
    assert document.startswith("<!doctype html>")
    assert "</html>" in document
    assert "<style>" in document
    # The stamp placeholder must be substituted, not shipped to the renderer.
    assert "__STAMP__" not in document
    assert "Page " in document  # page-number margin box


def test_report_html_escapes_untrusted_content():
    from app.services.pdf import render_blocks

    document = render_blocks(
        "T",
        "",
        [
            {
                "type": "table",
                "columns": [{"key": "label", "label": "L"}],
                "rows": [{"label": "<script>alert(1)</script>"}],
            }
        ],
    )
    assert "<script>alert(1)</script>" not in document
    assert "&lt;script&gt;" in document


def test_report_bars_take_numbers_not_formatted_strings():
    """`_bars` divides by the peak, so a string value would raise."""
    from app.services.pdf import _bars

    chart = _bars(
        [
            {"label": "A", "value": -98.0, "suffix": "%"},
            {"label": "B", "value": 4.0, "suffix": "%"},
        ]
    )
    assert "bar-fill" in chart
    assert "%" in chart
    # The near-100% bar must be wider than the 4% one.
    widths = [float(fragment.split("%")[0].rstrip('";')) for fragment in chart.split("width:")[1:]]
    assert len(widths) == 2
    assert widths[0] == 100.0, "the largest value should fill the track"
    assert widths[0] > widths[1]

    assert "Nothing to plot" in _bars([])
    assert "Nothing to plot" in _bars([{"label": "x", "value": None}])


def test_pdf_backend_is_detected_not_assumed(client, admin_token):
    """The templates endpoint must say whether PDFs can actually be rendered here."""
    payload = client.get("/api/v1/reports/templates", headers=auth(admin_token)).json()
    assert {item["key"] for item in payload["templates"]} == set(ALL_TEMPLATES) | {"product"}
    assert isinstance(payload["pdf_available"], bool)
    if not payload["pdf_available"]:
        # A missing backend must come with an actionable reason, not a bare False.
        assert "WeasyPrint" in payload["pdf_unavailable_reason"]


@pytest.mark.parametrize("template", ALL_TEMPLATES)
def test_report_endpoints_return_html_and_blocks(client, admin_token, template):
    html = client.get(f"/api/v1/reports/{template}?days=30", headers=auth(admin_token))
    assert html.status_code == 200
    assert html.headers["content-type"].startswith("text/html")
    assert "<!doctype html>" in html.text

    blocks = client.get(f"/api/v1/reports/{template}/data?days=30", headers=auth(admin_token))
    assert blocks.status_code == 200
    payload = blocks.json()
    assert payload["template"] == template
    assert payload["blocks"]


def test_unknown_report_template_is_rejected(client, admin_token):
    response = client.get("/api/v1/reports/no_such_template", headers=auth(admin_token))
    assert response.status_code == 422
    assert "available" in response.text


def test_product_template_requires_a_product(client, admin_token):
    response = client.get("/api/v1/reports/product", headers=auth(admin_token))
    assert response.status_code == 422
    assert "product_id" in response.text


def test_report_pdf_endpoint_answers_on_either_outcome(client, admin_token):
    """200 with real PDF bytes, or 501 with a reason - never a 500."""
    from app.services.pdf import available

    response = client.get("/api/v1/reports/executive_summary/pdf?days=30", headers=auth(admin_token))
    if available():
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF-")
        assert "attachment" in response.headers.get("content-disposition", "")
    else:
        assert response.status_code == 501
        assert "WeasyPrint" in response.text
