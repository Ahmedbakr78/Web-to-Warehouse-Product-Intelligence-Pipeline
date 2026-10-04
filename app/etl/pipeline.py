"""End-to-end ETL pipeline orchestrator.

Stages (each one is independently callable and instrumented):

``extract`` -> ``stage`` -> ``transform`` -> ``resolve`` -> ``load`` ->
``detect`` -> ``reconcile`` -> ``quality`` -> ``aggregate``

The orchestrator is used by the CLI, the REST API (manual trigger) and the Airflow
DAG, so behaviour is identical no matter how the run was started.
"""

from __future__ import annotations

import datetime as dt
import time
import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import session_scope
from app.core.errors import PipelineError
from app.core.logging import get_logger
from app.etl.bootstrap import sync_dim_source
from app.etl.catalog_reconcile import CatalogReconciler, reconciliation_summary
from app.etl.dq import QualityReport, evaluate_quality
from app.etl.loader import LoadStats, WarehouseLoader
from app.ingestion.base import NormalizedProduct, ProductSource, get_source, transform_product
from app.ingestion.dedupe import DedupeEngine
from app.models import DimSource
from app.models.operations import EtlRun, IngestionHttpLog

log = get_logger(__name__)

STAGE_NAMES = (
    "extract",
    "stage",
    "transform",
    "resolve",
    "load",
    "detect",
    "reconcile",
    "quality",
    "aggregate",
)


@dataclass
class PipelineConfig:
    """Everything the pipeline needs to know for one run."""

    sources: list[str] = field(default_factory=list)
    database: str | None = None
    limit_per_source: int | None = None
    strict: bool = False
    skip_dq: bool = False
    skip_catalog: bool = False
    skip_removed: bool = False
    stale_after_days: int = 7
    trigger: str = "manual"
    dag_id: str | None = None
    task_id: str | None = None
    created_by: str | None = None
    run_key: str | None = None
    dry_run: bool = False
    seed: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "sources": self.sources,
            "database": self.database,
            "limit_per_source": self.limit_per_source,
            "strict": self.strict,
            "skip_dq": self.skip_dq,
            "skip_catalog": self.skip_catalog,
            "stale_after_days": self.stale_after_days,
            "trigger": self.trigger,
            "dry_run": self.dry_run,
        }


@dataclass
class StageTiming:
    name: str
    duration_ms: float
    rows: int = 0
    detail: str = ""


@dataclass
class PipelineResult:
    """Full outcome of one pipeline execution."""

    run_id: str
    status: str = "running"
    database: str = ""
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None
    duration_ms: float | None = None
    counters: dict[str, int] = field(default_factory=dict)
    quality: dict[str, Any] | None = None
    reconciliation: dict[str, Any] | None = None
    timings: list[StageTiming] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sources_processed: list[str] = field(default_factory=list)
    sources_failed: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == "success"

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "database": self.database,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "counters": self.counters,
            "quality": self.quality,
            "reconciliation": self.reconciliation,
            "timings": [
                {"stage": t.name, "duration_ms": t.duration_ms, "rows": t.rows, "detail": t.detail}
                for t in self.timings
            ],
            "warnings": self.warnings,
            "sources_processed": self.sources_processed,
            "sources_failed": self.sources_failed,
            "error": self.error,
        }


class Pipeline:
    """Executable pipeline. ``Pipeline(config).run()`` returns a :class:`PipelineResult`."""

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self.result: PipelineResult | None = None

    # ------------------------------------------------------------------ context
    @contextmanager
    def _timer(self, name: str) -> Iterator[dict[str, Any]]:
        started = time.perf_counter()
        meta: dict[str, Any] = {"rows": 0, "detail": ""}
        try:
            yield meta
        finally:
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            assert self.result is not None
            self.result.timings.append(
                StageTiming(name, elapsed, int(meta.get("rows", 0)), meta.get("detail", ""))
            )

    def _run_row(self, session: Session) -> EtlRun:
        run_id = self.result.run_id  # type: ignore[union-attr]
        row = session.get(EtlRun, run_id)
        if row is None:
            row = EtlRun(run_id=run_id, pipeline="product_intelligence")
            session.add(row)
        row.run_key = self.config.run_key or run_id[:8]
        row.target_database = (self.config.database or settings.active_database).lower()
        row.status = "running"
        row.trigger = self.config.trigger
        row.dag_id = self.config.dag_id
        row.task_id = self.config.task_id
        row.started_at = dt.datetime.now(dt.timezone.utc)
        row.params = self.config.as_dict()
        row.created_by = self.config.created_by
        session.flush()
        return row

    def _source_codes(self) -> list[str]:
        if self.config.sources:
            return list(dict.fromkeys(self.config.sources))
        from app.ingestion.base import list_sources

        return [
            source["code"]
            for source in list_sources()
            if source.get("enabled") and source.get("terms_allowed", True)
        ]

    # ------------------------------------------------------------------ main
    def run(self) -> PipelineResult:
        database = (self.config.database or settings.active_database).lower()
        self.result = PipelineResult(
            run_id=uuid.uuid4().hex[:32],
            database=database,
            started_at=dt.datetime.now(dt.timezone.utc),
        )
        run_id = self.result.run_id
        log.info("pipeline run=%s database=%s sources=%s", run_id, database, self._source_codes())

        try:
            with session_scope(database) as session:
                self._execute(session, run_id)
        except PipelineError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("pipeline run failed")
            self._mark_failed(run_id, database, f"{type(exc).__name__}: {exc}")
            self.result.status = "failed"
            self.result.error = f"{type(exc).__name__}: {exc}"
            return self.result

        return self.result

    def _mark_failed(self, run_id: str, database: str, message: str) -> None:
        try:
            with session_scope(database) as session:
                row = session.get(EtlRun, run_id)
                if row is not None:
                    row.status = "failed"
                    row.error_message = message[:4000]
                    row.finished_at = dt.datetime.now(dt.timezone.utc)
        except Exception:  # pragma: no cover
            log.exception("could not persist failure state for run %s", run_id)

    # ------------------------------------------------------------------ stages
    def _execute(self, session: Session, run_id: str) -> None:
        result = self.result
        assert result is not None
        run_row = self._run_row(session)
        stats = LoadStats()
        dedupe = DedupeEngine(
            session,
            threshold=settings.dedupe_similarity_threshold,
            blocking_length=settings.dedupe_blocking_key_length,
            candidate_limit=settings.dedupe_candidate_limit,
        )

        for code in self._source_codes():
            source_started = time.perf_counter()
            try:
                source = get_source(code, run_id=run_id)
                source_stats = self._process_source(session, run_id, source, dedupe)
                stats.merge(source_stats)
                result.sources_processed.append(code)
                self._register_source_dim(
                    session, source, source_stats, time.perf_counter() - source_started, success=True
                )
            except Exception as exc:
                message = f"{type(exc).__name__}: {str(exc).splitlines()[0][:220]}"
                log.warning("source %s failed: %s", code, message, exc_info=settings.app_debug)
                result.sources_failed.append(code)
                result.warnings.append(f"{code}: {message}")
                self._register_source_dim(
                    session,
                    None,
                    LoadStats(),
                    time.perf_counter() - source_started,
                    success=False,
                    code=code,
                    message=message,
                )
                if self.config.strict or settings.pipeline_fail_fast:
                    raise

        # ---- aggregates
        with self._timer("aggregate") as meta:
            loader = WarehouseLoader(session, run_id)
            meta["rows"] = loader.refresh_category_daily()
            meta["detail"] = f"{meta['rows']} category-day aggregates"

        # ---- catalog reconciliation
        reconciliation: dict[str, Any] | None = None
        if not self.config.skip_catalog:
            with self._timer("reconcile") as meta:
                reconciler = CatalogReconciler(session, run_id)
                matches = reconciler.run(persist=not self.config.dry_run)
                reconciliation = reconciliation_summary(matches)
                meta["rows"] = len(matches)
                meta["detail"] = f"{reconciliation['matched']}/{reconciliation['total']} catalog SKUs matched"

        # ---- data quality
        quality: dict[str, Any] | None = None
        if not self.config.skip_dq:
            with self._timer("quality") as meta:
                report: QualityReport = evaluate_quality(session, run_id)
                quality = report.summary()
                meta["rows"] = len(report.outcomes)
                meta["detail"] = (
                    f"score {report.score} ({report.passed} pass / {report.warned} warn / {report.failed} fail)"
                )

        # ---- finalise
        finished = dt.datetime.now(dt.timezone.utc)
        run_row.finished_at = finished
        run_row.duration_ms = int((finished - run_row.started_at).total_seconds() * 1000)
        run_row.records_extracted = stats.staged
        run_row.records_valid = stats.snapshots_inserted
        run_row.records_rejected = stats.rejected
        run_row.records_inserted = stats.products_created
        run_row.records_updated = stats.products_updated
        run_row.duplicates_merged = stats.duplicates_merged
        run_row.new_products = stats.new_products
        run_row.price_changes = stats.price_changes
        run_row.removed_products = stats.removed_products
        run_row.catalog_matched = (reconciliation or {}).get("matched", 0)
        run_row.dq_passed = (quality or {}).get("pass", 0)
        run_row.dq_failed = (quality or {}).get("fail", 0)
        run_row.dq_score = (quality or {}).get("score")
        run_row.warnings = result.warnings[:20]
        blocking = (quality or {}).get("blocking") or []
        run_row.status = "failed" if blocking else ("partial" if result.sources_failed else "success")
        if result.sources_failed and run_row.status == "success":
            run_row.status = "partial"
        run_row.error_message = "; ".join(result.warnings)[:4000] if result.warnings else None

        result.status = run_row.status
        result.counters = stats.as_dict()
        result.quality = quality
        result.reconciliation = reconciliation
        result.finished_at = finished
        result.duration_ms = run_row.duration_ms
        session.flush()
        log.info(
            "pipeline finished run=%s status=%s snapshots=%d products=%d changes=%d quality=%s",
            run_id,
            result.status,
            stats.snapshots_inserted,
            stats.products_created,
            stats.price_changes,
            (quality or {}).get("score"),
        )

    # ------------------------------------------------------------------ per source
    def _process_source(
        self, session: Session, run_id: str, source: ProductSource, dedupe: DedupeEngine
    ) -> LoadStats:
        result = self.result
        assert result is not None
        limit = self.config.limit_per_source or settings.max_products_per_source
        loader = WarehouseLoader(session, run_id)
        stats = loader.stats
        loader.preload_dimensions()

        # The dimension row must exist before any fact references it (FK integrity).
        dim_source = sync_dim_source(session, source)
        session.flush()

        # ---- extract + stage
        with self._timer("extract") as meta:
            raw_records = list(_safe_take(source.fetch(limit=limit), limit))
            meta["rows"] = len(raw_records)
            meta["detail"] = f"{source.code} -> {len(raw_records)} records in {source.http_calls} http calls"

        with self._timer("stage") as meta:
            meta["rows"] = loader.stage(raw_records)

        # ---- transform
        normalized: list[NormalizedProduct] = []
        rejected: list[tuple[Any, str]] = []
        with self._timer("transform") as meta:
            by_key: dict[tuple[str, str], NormalizedProduct] = {}
            for raw in raw_records:
                record = transform_product(raw, strict=self.config.strict)
                if record.is_valid:
                    key = (record.source_code, record.source_product_id)
                    if key in by_key:  # intra-source duplicate rows
                        rejected.append((None, "duplicate_source_row"))
                        continue
                    by_key[key] = record
                    normalized.append(record)
                else:
                    rejected.append((None, record.reject_reason or "validation_failed"))
            meta["rows"] = len(normalized)
            meta["detail"] = f"{len(normalized)} valid / {len(rejected)} rejected"

        # ---- resolve (deduplicate) + upsert the canonical product
        resolved: list[tuple[NormalizedProduct, Any, Any]] = []
        with self._timer("resolve") as meta:
            for record in normalized:
                match = dedupe.find_match(record.canonical_name, brand=record.brand, category=record.category)
                product, created = loader.upsert_product(record, match)
                if created or match.is_duplicate:
                    dedupe.register(product)
                if match.is_duplicate and match.strategy == "fuzzy":
                    loader.stats.duplicates_merged += 1
                resolved.append((record, match, product))
            loader.flush()
            meta["rows"] = len(normalized)
            meta["detail"] = (
                f"{dedupe.stats.exact} exact / {dedupe.stats.fuzzy} fuzzy matches over "
                f"{dedupe.stats.blocked_comparisons} candidate comparisons"
            )

        # ---- load snapshots + detect changes
        seen_products: set[int] = set()
        with self._timer("load") as meta:
            latest = loader.preload_latest({product.product_id for _r, _m, product in resolved}, source.code)
            skipped_duplicates = 0
            for record, _match, product in resolved:
                # Two upstream rows can legitimately resolve to the same canonical
                # product (that *is* duplicate detection working). The fact table grain
                # is one row per product per run, so only the first one is stored.
                if product.product_id in seen_products:
                    skipped_duplicates += 1
                    loader.stats.duplicates_merged += 1
                    continue
                seen_products.add(product.product_id)
                previous = latest.get(product.product_id)
                loader.insert_snapshot(product, record, previous=previous)
            loader.flush()
            meta["rows"] = loader.stats.snapshots_inserted
            meta["detail"] = f"{skipped_duplicates} intra-run duplicates collapsed"

        with self._timer("detect") as meta:
            if not self.config.skip_removed:
                loader.detect_removed(source.code, seen_products, staleness_days=self.config.stale_after_days)
            loader.flush()
            meta["rows"] = stats.price_changes + stats.new_products + stats.removed_products
            meta["detail"] = (
                f"{stats.new_products} new, {stats.price_changes} price changes, "
                f"{stats.removed_products} removed, {stats.category_changes} category changes"
            )

        # ---- HTTP compliance audit
        if source._client is not None and not self.config.dry_run:
            rows = source._client.audit_rows()
            if rows:
                session.execute(sa.insert(IngestionHttpLog), rows)
                session.flush()
            stats.http_log_rows = len(rows)

        if source.errors:
            result.warnings.extend(source.errors[:5])

        loader.stats.staged = len(raw_records)
        loader.stats.rejected = len(rejected)
        loader.update_sync_state(
            source.code,
            extracted=loader.stats.staged,
            success=True,
            message=f"{loader.stats.staged} extracted, {loader.stats.snapshots_inserted} loaded",
        )
        return loader.stats

    def _register_source_dim(
        self,
        session: Session,
        source: ProductSource | None,
        stats: LoadStats,
        duration: float,
        *,
        success: bool,
        code: str | None = None,
        message: str | None = None,
    ) -> None:
        if source is None:
            if not code:
                return
            row = session.get(DimSource, code)
            if row is None:
                return
            row.last_run_at = dt.datetime.now(dt.timezone.utc)
            row.total_runs = (row.total_runs or 0) + 1
            return
        row = session.get(DimSource, source.code) or sync_dim_source(session, source)
        row.total_records = (row.total_records or 0) + stats.staged
        row.total_runs = (row.total_runs or 0) + 1
        row.last_run_at = dt.datetime.now(dt.timezone.utc)
        runs = max(row.total_runs, 1)
        row.avg_duration_seconds = round(((row.avg_duration_seconds or 0) * (runs - 1) + duration) / runs, 3)
        row.success_rate_pct = round(
            ((row.success_rate_pct or 0) * (runs - 1) + (100.0 if success else 0.0)) / runs, 2
        )
        session.flush()


def _safe_take(iterator: Iterable[Any], limit: int) -> Iterator[Any]:
    """Bound a source generator so a misbehaving source cannot hang the run."""
    count = 0
    for item in iterator:
        if count >= limit:
            break
        yield item
        count += 1


def run_pipeline(config: PipelineConfig | None = None) -> PipelineResult:
    """Convenience wrapper used by the CLI, API and Airflow."""
    return Pipeline(config).run()


__all__ = [
    "Pipeline",
    "PipelineConfig",
    "PipelineResult",
    "StageTiming",
    "run_pipeline",
    "STAGE_NAMES",
]
