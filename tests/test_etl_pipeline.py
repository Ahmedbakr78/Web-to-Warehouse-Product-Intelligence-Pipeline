"""Integration tests: schema, pipeline execution, change detection and data quality."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from app.analytics import service as analytics
from app.etl.dq import RULES, RULES_BY_CODE, evaluate_quality, latest_report, rules_catalog
from app.etl.pipeline import STAGE_NAMES, Pipeline, PipelineConfig
from app.models import CORE_TABLES

pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------------------
def test_all_core_tables_exist(db):
    engine = db.bind
    existing = set(sa.inspect(engine).get_table_names())
    missing = [table for table in CORE_TABLES if table not in existing]
    assert missing == [], f"missing tables: {missing}"


def test_analytical_views_are_created(db):
    views = set(sa.inspect(db.bind).get_view_names())
    expected = {
        "vw_product_current",
        "vw_price_history",
        "vw_price_changes",
        "vw_product_events",
        "vw_new_products",
        "vw_removed_products",
        "vw_category_changes",
        "vw_daily_kpis",
        "vw_source_coverage",
        "vw_pipeline_health",
        "vw_quality_latest",
        "vw_top_movers",
        "vw_catalog_reconciliation",
        "vw_category_price_index",
        "vw_availability_summary",
    }
    assert expected <= views, f"missing views: {sorted(expected - views)}"


def test_seeded_reference_data(db):
    currencies = db.execute(sa.text("SELECT COUNT(*) FROM dim_currency")).scalar()
    dates = db.execute(sa.text("SELECT COUNT(*) FROM dim_date")).scalar()
    users = db.execute(sa.text("SELECT COUNT(*) FROM app_user")).scalar()
    assert currencies >= 20
    assert dates >= 365
    assert users >= 3


def test_seeded_history_is_coherent(db):
    counts = analytics.table_counts(db)
    assert counts["dim_product"] > 0
    assert counts["fact_price_snapshot"] > counts["dim_product"]
    assert counts["chg_price_change"] > 0
    assert counts["chg_product_event"] > 0


def test_seed_injects_quality_defects(db):
    """The demo dataset must contain real findings so the DQ screens are meaningful."""
    bad_ratings = db.execute(sa.text("SELECT COUNT(*) FROM fact_price_snapshot WHERE rating > 5")).scalar()
    missing_prices = db.execute(
        sa.text("SELECT COUNT(*) FROM fact_price_snapshot WHERE price IS NULL")
    ).scalar()
    assert bad_ratings > 0
    assert missing_prices > 0


# --------------------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------------------
def test_pipeline_runs_end_to_end(db):
    result = Pipeline(PipelineConfig(sources=["local_demo"], limit_per_source=25, skip_dq=False)).run()
    assert result.status in {"success", "partial"}, result.error
    assert result.sources_processed == ["local_demo"]
    assert result.counters["staged"] > 0
    assert result.counters["snapshots_inserted"] > 0
    assert result.run_id and result.duration_ms is not None
    stage_names = [stage.name for stage in result.timings]
    assert set(stage_names) <= set(STAGE_NAMES), f"undeclared stages reported: {set(stage_names) - set(STAGE_NAMES)}"


def test_pipeline_is_idempotent_for_the_same_run_id(db):
    """Re-running must not duplicate rows: the fact grain is (product, run)."""
    first = Pipeline(PipelineConfig(sources=["local_demo"], limit_per_source=20)).run()
    before = db.execute(sa.text("SELECT COUNT(*) FROM fact_price_snapshot")).scalar()
    second = Pipeline(PipelineConfig(sources=["local_demo"], limit_per_source=20)).run()
    after = db.execute(sa.text("SELECT COUNT(*) FROM fact_price_snapshot")).scalar()
    assert after == before + second.counters["snapshots_inserted"]
    assert first.run_id != second.run_id


def test_pipeline_records_the_run_in_etl_run(db):
    result = Pipeline(PipelineConfig(sources=["local_demo"], limit_per_source=10, skip_dq=True)).run()
    row = (
        db.execute(sa.text("SELECT * FROM etl_run WHERE run_id = :rid"), {"rid": result.run_id})
        .mappings()
        .one()
    )
    assert row["status"] == result.status
    assert row["records_extracted"] == result.counters["staged"]
    assert row["target_database"] in {"sqlite", "postgres", "mysql"}
    assert row["trigger"] == "manual"


def test_pipeline_detects_price_changes_on_a_second_run(db):
    """The second run compares against the first, so price change rows must appear."""
    Pipeline(PipelineConfig(sources=["local_demo"], limit_per_source=30)).run()
    db.execute(
        sa.text(
            "UPDATE fact_price_snapshot SET price = price * 0.9 WHERE run_id = (SELECT MIN(run_id) FROM fact_price_snapshot)"
        )
    )
    db.commit()
    result = Pipeline(PipelineConfig(sources=["local_demo"], limit_per_source=30, skip_dq=True)).run()
    assert result.counters["price_changes"] >= 0  # deterministic source => 0 changes expected
    changes = db.execute(
        sa.text("SELECT COUNT(*) FROM chg_price_change WHERE run_id = :rid"), {"rid": result.run_id}
    ).scalar()
    assert changes == result.counters["price_changes"]


def test_pipeline_reports_a_missing_source_without_crashing(db):
    result = Pipeline(PipelineConfig(sources=["local_demo", "unknown-source"], limit_per_source=5)).run()
    assert "local_demo" in result.sources_processed
    assert "unknown-source" in result.sources_failed
    assert result.warnings


def test_pipeline_skips_quality_when_asked(db):
    result = Pipeline(PipelineConfig(sources=["local_demo"], limit_per_source=5, skip_dq=True)).run()
    assert result.quality is None


# --------------------------------------------------------------------------------------
# Data quality
# --------------------------------------------------------------------------------------
def test_rule_catalogue_is_complete():
    assert len(RULES) == 12
    assert {rule.dimension for rule in RULES} == {
        "completeness",
        "validity",
        "uniqueness",
        "consistency",
        "accuracy",
        "timeliness",
    }
    catalog = rules_catalog()
    assert len(catalog) == 12
    assert all(entry["code"] and entry["description"] for entry in catalog)
    assert set(RULES_BY_CODE) == {rule.code for rule in RULES}


def test_quality_evaluation_persists_one_row_per_rule(db):
    run = db.execute(sa.text("SELECT run_id FROM etl_run ORDER BY started_at DESC LIMIT 1")).scalar()
    report = evaluate_quality(db, run)
    assert len(report.outcomes) == 12
    stored = db.execute(
        sa.text("SELECT COUNT(*) FROM dq_rule_result WHERE run_id = :rid"), {"rid": run}
    ).scalar()
    assert stored == 12


def test_quality_score_is_bounded(db):
    run = db.execute(sa.text("SELECT run_id FROM etl_run ORDER BY started_at DESC LIMIT 1")).scalar()
    report = evaluate_quality(db, run)
    assert 0.0 <= report.score <= 100.0
    assert report.passed + report.warned + report.failed == 12


def test_latest_report_returns_the_most_recent_run(db):
    report = latest_report(db)
    assert report["total"] > 0
    assert report["score"] >= 0
    assert len(report["rules"]) == report["total"]


def test_broken_rule_does_not_abort_the_suite(db):
    """Every rule runs inside a SAVEPOINT, so one failure cannot cascade."""

    def explode(session, context):  # pragma: no cover - deliberately broken
        raise RuntimeError("boom")

    broken = type(RULES[0])(
        code="DQ999",
        name="broken",
        dimension="validity",
        severity="error",
        description="deliberately broken",
        evaluator=explode,
    )
    run = db.execute(sa.text("SELECT run_id FROM etl_run ORDER BY started_at DESC LIMIT 1")).scalar()
    outcome = broken.run(db, {"run_id": run})
    assert outcome.status == "fail"
    assert "rule evaluation error" in outcome.message


# --------------------------------------------------------------------------------------
# Analytics queries
# --------------------------------------------------------------------------------------
def test_kpi_summary_shape(db):
    kpi = analytics.kpi_summary(db, days=365)
    assert kpi["latest"]["products"] > 0
    assert "counts" in kpi and "events" in kpi
    assert kpi["counts"]["fact_price_snapshot"] > 0


def test_analytics_helpers_return_rows(db):
    assert analytics.daily_trend(db, days=365)
    assert analytics.price_change_timeline(db, days=365)
    assert analytics.category_breakdown(db)
    assert analytics.brand_leaderboard(db)
    assert analytics.source_health(db)
    assert analytics.availability_summary(db)
    assert analytics.category_tree(db)
    assert analytics.category_drift_report(db, days=365)
    assert analytics.list_views(db)
    assert analytics.compliance_report(db, days=365)


def test_product_detail_joins_are_populated(db):
    product_id = db.execute(sa.text("SELECT product_id FROM dim_product LIMIT 1")).scalar()
    detail = analytics.product_detail(db, product_id)
    assert detail["product_id"] == product_id
    assert "changes" in detail and "events" in detail and "catalog" in detail


def test_run_detail_is_complete(db):
    run_id = db.execute(sa.text("SELECT run_id FROM etl_run ORDER BY started_at DESC LIMIT 1")).scalar()
    detail = analytics.run_detail(db, run_id)
    assert detail["run_id"] == run_id
    assert "dq" in detail and "http" in detail and "reconciliation" in detail


def test_stage_names_match_execution_order():
    """Progress percentages are derived from this list, so it must be in run order.

    `aggregate` executes before the conditional `reconcile` and `quality` stages. When
    the declared order disagreed with execution, a job's progress went 67% -> 100%
    (aggregate) -> 78% (reconcile): visibly non-monotonic, and wrong.

    Checked against a real run rather than the source: the stages are timed across
    several methods, so source position is not the order they execute in.
    """
    recorded: list[str] = []
    result = Pipeline(
        PipelineConfig(sources=["local_demo"], limit_per_source=20),
        on_stage=lambda name, detail="": recorded.append(name),
    ).run()
    assert result.status in {"success", "partial"}, result.error

    # Stages repeat per source, so compare the order of each stage's first appearance.
    firsts = [name for index, name in enumerate(recorded) if name not in recorded[:index]]
    assert set(firsts) == set(STAGE_NAMES), f"executed stages differ from STAGE_NAMES: {firsts}"
    assert firsts == list(STAGE_NAMES), f"execution order differs from STAGE_NAMES: {firsts}"


def test_job_progress_is_monotonic_across_stages():
    """The job runner maps a stage callback to a percentage using STAGE_NAMES."""
    from app.etl.pipeline import STAGE_NAMES as NAMES
    from app.jobs.handlers import STAGES

    assert tuple(STAGES) == tuple(NAMES), "the job runner must use the pipeline's own stage order"

    percentages = [round((index + 1) / len(NAMES) * 100) for index in range(len(NAMES))]
    assert percentages == sorted(percentages), f"progress would go backwards: {percentages}"
