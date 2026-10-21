"""Market analytics: buckets, spread, movers, lifecycle, anomalies and risk."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.security import create_access_token

pytestmark = pytest.mark.integration


@pytest.fixture()
def client(clean_database):
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


def test_price_buckets_cover_the_catalogue(client, viewer_token):
    rows = client.get("/api/v1/analytics/price-buckets", headers=auth(viewer_token)).json()
    assert isinstance(rows, list) and rows
    keys = {row["bucket"] for row in rows}
    assert keys <= {"under_10", "from_10_to_50", "from_50_to_200", "from_200_to_1000", "over_1000", "unknown"}
    assert sum(row["listings"] for row in rows) > 0
    for row in rows:
        assert set(row) >= {"bucket", "listings", "in_stock_count", "avg_rating"}


def test_source_spread_ranks_multi_source_products(client, viewer_token):
    rows = client.get("/api/v1/analytics/source-spread?limit=20", headers=auth(viewer_token)).json()
    assert isinstance(rows, list)
    for row in rows:
        assert row["sources"] > 1
        assert row["min_price_usd"] <= row["avg_price_usd"] <= row["max_price_usd"]
        assert row["spread_pct"] >= 0
        assert set(row) >= {"canonical_name", "sources", "min_price_usd", "max_price_usd", "spread_pct"}


def test_source_spread_finds_a_genuinely_overlapping_product(db):
    """The overlap analytics must work when the data actually overlaps.

    The seeded corpus samples each source independently, so no two sources
    share a product and the cross-source panels are legitimately empty. That
    made it possible for the grouping to be wrong and still pass every test:
    an empty list satisfies every ordering assertion. This test injects a
    product listed by two sources at two different prices and requires the
    analytics to find it.
    """
    import datetime as dt

    from app.ingestion.cleaning import name_fingerprint
    from app.models.dimensions import DimProduct
    from app.models.facts import FactPriceSnapshot
    from app.models.operations import EtlRun

    fingerprint = name_fingerprint("Shared Test Widget", "Acme")
    now = dt.datetime.now(dt.timezone.utc)
    db.add(
        EtlRun(
            run_id="overlap-run",
            pipeline="product_intelligence",
            target_database="sqlite",
            status="success",
            started_at=now,
            finished_at=now,
        )
    )
    db.flush()
    for suffix, source, price in (("a", "gutendex_books", 10.0), ("b", "openlibrary_books", 30.0)):
        product = DimProduct(
            source_product_id=f"overlap-{suffix}",
            source_code=source,
            canonical_name="Shared Test Widget",
            normalized_name="shared test widget",
            display_name="Shared Test Widget",
            brand="Acme",
            currency="USD",
            current_price=price,
            availability="in_stock",
            fingerprint=fingerprint,
            match_strategy="exact",
            match_score=1.0,
            is_active=True,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(product)
        db.flush()
        # The analytics read the *fact* table through vw_product_current, so a
        # dimension row on its own would not be visible to them.
        db.add(
            FactPriceSnapshot(
                product_id=product.product_id,
                source_code=source,
                run_id="overlap-run",
                date_id=int(now.strftime("%Y%m%d")),
                captured_at=now,
                price=price,
                price_usd=price,
                currency="USD",
                fx_rate_to_usd=1.0,
                availability="in_stock",
                in_stock=True,
                is_first_sighting=True,
            )
        )
    db.flush()

    from app.analytics.service import cross_source_spread, source_overlap

    spread = cross_source_spread(db, limit=50)
    matched = [row for row in spread if row["canonical_name"] == "Shared Test Widget"]
    assert matched, "the cross-source spread did not find an overlapping product"
    assert matched[0]["sources"] == 2
    assert matched[0]["min_price_usd"] == 10.0
    assert matched[0]["max_price_usd"] == 30.0
    assert matched[0]["spread_pct"] > 0

    pairs = source_overlap(db)
    pair = next(
        (
            row
            for row in pairs
            if {row["source_a"], row["source_b"]} == {"gutendex_books", "openlibrary_books"}
        ),
        None,
    )
    assert pair is not None, "the source overlap did not report the shared product"
    assert pair["shared_products"] >= 1


def test_category_movers_rank_by_magnitude(client, viewer_token):
    rows = client.get(
        "/api/v1/analytics/category-movers?days=120&limit=20", headers=auth(viewer_token)
    ).json()
    assert isinstance(rows, list) and rows
    magnitudes = [row["avg_abs_change_pct"] for row in rows]
    assert magnitudes == sorted(magnitudes, reverse=True)
    for row in rows:
        assert row["increases"] + row["decreases"] <= row["changes"]
        assert set(row) >= {"category_name", "changes", "avg_abs_change_pct", "max_abs_change_pct"}


def test_event_timeline_merges_lifecycle_and_price_changes(client, viewer_token):
    rows = client.get("/api/v1/analytics/event-timeline?days=120", headers=auth(viewer_token)).json()
    assert isinstance(rows, list) and rows
    dates = [str(row["full_date"]) for row in rows]
    assert dates == sorted(dates)
    assert sum(row["price_changes"] for row in rows) > 0
    assert sum(row["total_events"] for row in rows) > 0
    for row in rows:
        assert set(row) >= {
            "full_date",
            "new_products",
            "removed_products",
            "recategorised",
            "total_events",
            "price_changes",
        }


def test_price_anomalies_are_ranked_by_z_score(client, viewer_token):
    rows = client.get("/api/v1/analytics/price-anomalies?limit=20", headers=auth(viewer_token)).json()
    assert isinstance(rows, list)
    scores = [abs(row["z_score"]) for row in rows]
    assert scores == sorted(scores, reverse=True)
    assert all(score >= 2.0 for score in scores)
    for row in rows:
        assert set(row) >= {
            "product_id",
            "canonical_name",
            "category_name",
            "source_code",
            "price_usd",
            "category_mean_usd",
            "z_score",
        }


def test_price_anomalies_are_actually_detected(client, viewer_token):
    """The detector must work on a real deviation, not a zeroed one.

    The portable variance expression is ``E[x^2] - (E[x])^2``. Computing it the
    other way round yields the *negative* variance for every real price
    distribution, which clamps the deviation to zero and silently disables the
    whole detector - while the ranking test above still passed, because an
    empty list is trivially sorted.

    The small seeded corpus may not contain a 2-sigma outlier, so the assertion
    is on the deviation itself: with an inverted variance every category
    collapses to a standard deviation of exactly zero.
    """
    index = client.get("/api/v1/analytics/category-index", headers=auth(viewer_token)).json()
    assert isinstance(index, list) and index
    deviations = [row.get("price_stddev") for row in index if row.get("price_stddev") is not None]
    assert deviations, "no category reports a price deviation at all"
    assert any(value > 0 for value in deviations), (
        "every category reports a zero price deviation - the variance is inverted again"
    )

    rows = client.get("/api/v1/analytics/price-anomalies?limit=50", headers=auth(viewer_token)).json()
    assert isinstance(rows, list)
    for row in rows:
        assert row["category_mean_usd"] is not None
        assert row["price_usd"] is not None
        assert abs(row["z_score"]) >= 2.0
        # A detected outlier really does sit away from its category mean.
        assert abs(row["price_usd"] - row["category_mean_usd"]) > 0


def test_category_price_index_reports_real_variance(client, viewer_token):
    """The category index must publish a non-zero deviation where there is one."""
    rows = client.get("/api/v1/analytics/category-index", headers=auth(viewer_token)).json()
    assert isinstance(rows, list) and rows
    spread = [row for row in rows if row.get("price_stddev") not in (None, 0)]
    assert spread, "every category reports a zero price deviation - the variance is inverted again"
    for row in spread:
        assert row["price_stddev"] > 0


def test_source_overlap_pairs_are_unique_and_ordered(client, viewer_token):
    rows = client.get("/api/v1/analytics/source-overlap", headers=auth(viewer_token)).json()
    assert isinstance(rows, list)
    pairs = [(row["source_a"], row["source_b"]) for row in rows]
    assert len(pairs) == len(set(pairs))
    assert all(a < b for a, b in pairs)
    counts = [row["shared_products"] for row in rows]
    assert counts == sorted(counts, reverse=True)
    assert all(count > 0 for count in counts)


def test_data_freshness_covers_every_source(client, viewer_token):
    rows = client.get("/api/v1/analytics/data-freshness?stale_days=7", headers=auth(viewer_token)).json()
    assert isinstance(rows, list) and rows
    for row in rows:
        assert set(row) >= {
            "source_code",
            "products",
            "active_products",
            "last_seen_at",
            "stale_products",
            "stale_pct",
        }
        assert row["stale_products"] <= row["products"]
        assert 0 <= (row["stale_pct"] or 0) <= 100


def test_inventory_risk_orders_by_stock_pressure(client, viewer_token):
    rows = client.get("/api/v1/analytics/inventory-risk?limit=20", headers=auth(viewer_token)).json()
    assert isinstance(rows, list) and rows
    counts = [row["out_of_stock_count"] for row in rows]
    assert counts == sorted(counts, reverse=True)
    for row in rows:
        assert set(row) >= {
            "category_name",
            "observations",
            "in_stock_pct",
            "out_of_stock_count",
            "price_increases",
        }


def test_currency_exposure_covers_active_listings(client, viewer_token):
    rows = client.get("/api/v1/analytics/currency-exposure", headers=auth(viewer_token)).json()
    assert isinstance(rows, list) and rows
    counts = [row["listings"] for row in rows]
    assert counts == sorted(counts, reverse=True)
    assert sum(counts) > 0
    for row in rows:
        assert set(row) >= {"currency", "listings", "sources", "in_stock_count", "avg_price_usd"}


def test_best_value_is_ranked_by_rating_per_dollar(client, viewer_token):
    rows = client.get("/api/v1/analytics/best-value?limit=20", headers=auth(viewer_token)).json()
    assert isinstance(rows, list)
    scores = [row["value_score"] for row in rows]
    assert scores == sorted(scores, reverse=True)
    for row in rows:
        assert row["rating"] >= 4.0
        assert (row["rating_count"] or 0) >= 10
        assert row["price_usd"] > 0
        assert set(row) >= {"product_id", "canonical_name", "price_usd", "rating", "value_score"}


def test_brand_momentum_ranks_winners_first(client, viewer_token):
    rows = client.get("/api/v1/analytics/brand-momentum?days=120&limit=20", headers=auth(viewer_token)).json()
    assert isinstance(rows, list) and rows
    avgs = [row["avg_change_pct"] for row in rows]
    assert avgs == sorted(avgs, reverse=True)
    for row in rows:
        assert row["increases"] + row["decreases"] <= row["changes"]
        assert row["brand"]
        assert set(row) >= {"brand", "changes", "avg_change_pct", "avg_abs_change_pct"}


def test_weekday_pattern_orders_monday_first(client, viewer_token):
    rows = client.get("/api/v1/analytics/weekday-pattern?days=120", headers=auth(viewer_token)).json()
    assert isinstance(rows, list) and rows
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    names = [row["day_name"] for row in rows]
    assert names == sorted(names, key=order.index)
    assert sum(row["changes"] for row in rows) > 0
    for row in rows:
        assert set(row) >= {
            "day_name",
            "is_weekend",
            "changes",
            "increases",
            "decreases",
            "avg_abs_change_pct",
        }


def test_market_endpoints_reject_anonymous_callers(client):
    for path in (
        "/api/v1/analytics/price-buckets",
        "/api/v1/analytics/source-spread",
        "/api/v1/analytics/category-movers",
        "/api/v1/analytics/event-timeline",
        "/api/v1/analytics/price-anomalies",
        "/api/v1/analytics/source-overlap",
        "/api/v1/analytics/data-freshness",
        "/api/v1/analytics/inventory-risk",
        "/api/v1/analytics/currency-exposure",
        "/api/v1/analytics/best-value",
        "/api/v1/analytics/brand-momentum",
        "/api/v1/analytics/weekday-pattern",
    ):
        response = client.get(path)
        assert response.status_code == 401
        # RFC 7235: the 401 names the scheme so clients can tell an expired
        # session from a forbidden role without parsing the body.
        assert response.headers.get("www-authenticate") == 'Bearer realm="pip"'


def test_expired_token_is_reported_as_expired(client):
    import jwt as pyjwt

    from app.core.config import settings

    expired = pyjwt.encode(
        {
            "sub": "1",
            "role": "admin",
            "type": "access",
            "iss": "product-intelligence-pipeline",
            "exp": 1,
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    response = client.get("/api/v1/analytics/price-buckets", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
    assert response.json()["details"].get("reason") == "expired"
