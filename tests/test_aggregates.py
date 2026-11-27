"""Regression tests for daily category aggregates in pipeline runs and demo seeds."""

from __future__ import annotations

import sqlalchemy as sa

from app.analytics.service import category_breakdown
from app.etl.bootstrap import bootstrap
from app.etl.pipeline import Pipeline, PipelineConfig
from app.etl.seed import seed_history
from app.models.facts import AggCategoryDaily


def test_seed_history_populates_agg_category_daily(tmp_path):
    """Demo seeding must compute agg_category_daily so Analytics never shows $0."""
    db_url = f"sqlite:///{tmp_path / 'seed_agg.db'}"
    bootstrap(db_url)

    from app.core.db import dispose_all, session_scope

    try:
        with session_scope(db_url) as session:
            result = seed_history(session, days=10, count=20)
            assert result["aggregates"] > 0

        with session_scope(db_url) as session:
            breakdown = category_breakdown(session, limit=20)
            assert len(breakdown) > 0
            total_obs = sum(int(row["observations"] or 0) for row in breakdown)
            assert total_obs > 0
            assert any(float(row["avg_price"] or 0) > 0 for row in breakdown)
            sample = session.execute(sa.select(AggCategoryDaily).limit(1)).scalars().first()
            assert sample is not None
            assert sample.median_price is not None
    finally:
        dispose_all()


def test_loader_refresh_category_daily_computes_median_and_correct_counts(tmp_path):
    """WarehouseLoader writes true median_price and unswapped new_product_count / avg_rating."""
    db_url = f"sqlite:///{tmp_path / 'loader_agg.db'}"
    bootstrap(db_url)

    from app.core.db import dispose_all, session_scope

    try:
        import os

        old_db = os.environ.get("DATABASE_URL")
        old_active = os.environ.get("ACTIVE_DATABASE")
        os.environ["DATABASE_URL"] = db_url
        os.environ["ACTIVE_DATABASE"] = "sqlite"
        dispose_all()

        # Run local_demo into the isolated SQLite target
        from app.core.config import settings

        prev_url, prev_active = settings.database_url, settings.active_database
        settings.database_url = db_url
        settings.active_database = "sqlite"
        try:
            run = Pipeline(
                PipelineConfig(sources=["local_demo"], limit_per_source=15, skip_catalog=True)
            ).run()
            assert run.status in {"success", "partial"}
        finally:
            settings.database_url = prev_url
            settings.active_database = prev_active

        with session_scope(db_url) as session:
            rows = session.execute(sa.select(AggCategoryDaily)).scalars().all()
            assert len(rows) > 0
            assert any(row.median_price is not None for row in rows)
            assert any((row.new_product_count or 0) >= 1 for row in rows)
            assert all(row.avg_rating is None or 0 <= float(row.avg_rating) <= 5 for row in rows)
    finally:
        if old_db is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_db
        if old_active is None:
            os.environ.pop("ACTIVE_DATABASE", None)
        else:
            os.environ["ACTIVE_DATABASE"] = old_active
        dispose_all()
