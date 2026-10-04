"""Data-quality framework (six dimensions of quality, rule-based, measurable).

Every rule is a small declarative object so it can be unit tested, re-used from the
CLI, the API and Airflow, and rendered in the dashboard.  Rules evaluate to
``pass`` / ``warn`` / ``fail`` with the observed and expected values stored for audit.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Callable

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.operations import DqRuleResult, EtlRun

log = get_logger(__name__)

DIMENSION_COMPLETENESS = "completeness"
DIMENSION_VALIDITY = "validity"
DIMENSION_UNIQUENESS = "uniqueness"
DIMENSION_CONSISTENCY = "consistency"
DIMENSION_ACCURACY = "accuracy"
DIMENSION_TIMELINESS = "timeliness"

SEVERITY_INFO = "info"
SEVERITY_WARN = "warn"
SEVERITY_ERROR = "error"
SEVERITY_CRITICAL = "critical"

_SEVERITY_ORDER = {SEVERITY_INFO: 0, SEVERITY_WARN: 1, SEVERITY_ERROR: 2, SEVERITY_CRITICAL: 3}


@dataclass
class RuleOutcome:
    """Result of one rule evaluation."""

    rule_code: str
    rule_name: str
    dimension: str
    severity: str
    status: str                      # pass | warn | fail
    observed_value: float | None = None
    expected_value: float | None = None
    threshold: float | None = None
    records_checked: int = 0
    records_failed: int = 0
    message: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def pass_rate_pct(self) -> float | None:
        if not self.records_checked:
            return None
        return round((1 - self.records_failed / self.records_checked) * 100, 4)


@dataclass
class QualityReport:
    """Aggregated DQ report for a single run."""

    run_id: str
    outcomes: list[RuleOutcome] = field(default_factory=list)
    duration_ms: float | None = None

    @property
    def passed(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "pass")

    @property
    def warned(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "warn")

    @property
    def failed(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "fail")

    @property
    def blocking_failures(self) -> list[RuleOutcome]:
        return [o for o in self.outcomes if o.status == "fail" and _SEVERITY_ORDER[o.severity] >= _SEVERITY_ORDER[SEVERITY_ERROR]]

    @property
    def score(self) -> float:
        """0-100 quality score weighted by severity."""
        if not self.outcomes:
            return 100.0
        total = 0.0
        for outcome in self.outcomes:
            weight = 1 + _SEVERITY_ORDER[outcome.severity] * 0.5
            factor = {"pass": 1.0, "warn": 0.75, "fail": 0.0}[outcome.status]
            total += weight * factor
        return round((total / sum(1 + _SEVERITY_ORDER[o.severity] * 0.5 for o in self.outcomes)) * 100, 2)

    def summary(self) -> dict[str, Any]:
        by_dimension: dict[str, dict[str, int]] = {}
        for outcome in self.outcomes:
            bucket = by_dimension.setdefault(outcome.dimension, {"pass": 0, "warn": 0, "fail": 0})
            bucket[outcome.status] += 1
        return {
            "run_id": self.run_id,
            "total": len(self.outcomes),
            "pass": self.passed,
            "warn": self.warned,
            "fail": self.failed,
            "score": self.score,
            "by_dimension": by_dimension,
            "blocking": [o.rule_code for o in self.blocking_failures],
        }


# --------------------------------------------------------------------------------------
# Rule definitions
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Rule:
    """Declarative data-quality rule."""

    code: str
    name: str
    dimension: str
    severity: str
    description: str
    evaluator: Callable[[Session, dict[str, Any]], RuleOutcome]

    def run(self, session: Session, context: dict[str, Any] | None = None) -> RuleOutcome:
        try:
            return self.evaluator(session, context or {})
        except Exception as exc:  # pragma: no cover - a broken rule must not kill the run
            log.exception("rule %s crashed", self.code)
            return RuleOutcome(
                rule_code=self.code,
                rule_name=self.name,
                dimension=self.dimension,
                severity=self.severity,
                status="fail",
                message=f"rule evaluation error: {type(exc).__name__}: {exc}",
            )


def _status(observed: float | None, threshold: float, higher_is_better: bool = True) -> str:
    if observed is None:
        return "fail"
    if higher_is_better:
        if observed >= threshold:
            return "pass"
        if observed >= threshold * 0.95:
            return "warn"
        return "fail"
    if observed <= threshold:
        return "pass"
    if observed <= threshold * 1.05:
        return "warn"
    return "fail"


# ---- individual evaluators -----------------------------------------------------------
def _completeness(session: Session, ctx: dict[str, Any]) -> RuleOutcome:
    """Every stored product must have a name, a price and a category."""
    run_id = ctx.get("run_id")
    total = session.execute(
        sa.select(sa.func.count()).select_from(sa.text("dim_product"))
    ).scalar() or 0
    incomplete = session.execute(
        sa.text(
            """
            SELECT COUNT(*) FROM dim_product
            WHERE is_active = 1
              AND (canonical_name IS NULL OR canonical_name = ''
                   OR category_id IS NULL
                   OR current_price IS NULL)
            """
        )
    ).scalar() or 0
    rate = 100.0 if total == 0 else (1 - incomplete / total) * 100
    return RuleOutcome(
        rule_code="DQ001",
        rule_name="Required fields populated",
        dimension=DIMENSION_COMPLETENESS,
        severity=SEVERITY_ERROR,
        status=_status(rate, 95.0),
        observed_value=round(rate, 4),
        expected_value=95.0,
        threshold=95.0,
        records_checked=total,
        records_failed=incomplete,
        message=f"{incomplete} of {total} active products are missing name/price/category",
        evidence={"run_id": run_id},
    )


def _valid_price(session: Session, ctx: dict[str, Any]) -> RuleOutcome:
    total, invalid = session.execute(
        sa.text(
            """
            SELECT COUNT(*),
                   COALESCE(SUM(CASE WHEN price < 0 OR price > 1000000 THEN 1 ELSE 0 END), 0)
            FROM fact_price_snapshot WHERE price IS NOT NULL
            """
        )
    ).one()
    rate = 100.0 if total == 0 else (1 - invalid / total) * 100
    return RuleOutcome(
        rule_code="DQ002",
        rule_name="Prices within valid range",
        dimension=DIMENSION_VALIDITY,
        severity=SEVERITY_ERROR,
        status=_status(rate, 99.0),
        observed_value=round(rate, 4),
        expected_value=99.0,
        threshold=99.0,
        records_checked=int(total),
        records_failed=int(invalid),
        message=f"{invalid} snapshots with a price outside 0 - 1,000,000",
    )


def _valid_rating(session: Session, ctx: dict[str, Any]) -> RuleOutcome:
    total, invalid = session.execute(
        sa.text(
            """
            SELECT COUNT(*),
                   COALESCE(SUM(CASE WHEN rating < 0 OR rating > 5 THEN 1 ELSE 0 END), 0)
            FROM fact_price_snapshot WHERE rating IS NOT NULL
            """
        )
    ).one()
    rate = 100.0 if total == 0 else (1 - invalid / total) * 100
    return RuleOutcome(
        rule_code="DQ003",
        rule_name="Ratings within 0-5 scale",
        dimension=DIMENSION_VALIDITY,
        severity=SEVERITY_ERROR,
        status=_status(rate, 98.0),
        observed_value=round(rate, 4),
        expected_value=98.0,
        threshold=98.0,
        records_checked=int(total),
        records_failed=int(invalid),
        message=f"{invalid} ratings outside the 0-5 scale (rescaling/normalisation defect)",
    )


def _currency_known(session: Session, ctx: dict[str, Any]) -> RuleOutcome:
    total, unknown = session.execute(
        sa.text(
            """
            SELECT COUNT(*),
                   COALESCE(SUM(CASE WHEN LOWER(currency) NOT IN
                        (SELECT LOWER(currency_code) FROM dim_currency) THEN 1 ELSE 0 END), 0)
            FROM fact_price_snapshot
            """
        )
    ).one()
    rate = 100.0 if total == 0 else (1 - unknown / total) * 100
    return RuleOutcome(
        rule_code="DQ004",
        rule_name="Currency codes known",
        dimension=DIMENSION_CONSISTENCY,
        severity=SEVERITY_ERROR,
        status=_status(rate, 100.0),
        observed_value=round(rate, 4),
        expected_value=100.0,
        threshold=100.0,
        records_checked=int(total),
        records_failed=int(unknown),
        message=f"{unknown} snapshots reference a currency missing from dim_currency",
    )


def _uniqueness_fingerprint(session: Session, ctx: dict[str, Any]) -> RuleOutcome:
    total, duplicates = session.execute(
        sa.text(
            """
            SELECT COUNT(*), COALESCE(SUM(CASE WHEN dup_count > 1 THEN dup_count - 1 ELSE 0 END), 0)
            FROM (
                SELECT fingerprint, COUNT(*) AS dup_count
                FROM dim_product WHERE is_active = 1
                GROUP BY fingerprint
            ) t
            """
        )
    ).one()
    rate = 100.0 if total == 0 else (1 - duplicates / total) * 100
    return RuleOutcome(
        rule_code="DQ005",
        rule_name="Product fingerprints unique",
        dimension=DIMENSION_UNIQUENESS,
        severity=SEVERITY_WARN,
        status=_status(rate, 99.5),
        observed_value=round(rate, 4),
        expected_value=99.5,
        threshold=99.5,
        records_checked=int(total),
        records_failed=int(duplicates),
        message=f"{duplicates} duplicate fingerprints among active products (dedupe gap)",
    )


def _unique_snapshot_grain(session: Session, ctx: dict[str, Any]) -> RuleOutcome:
    total, duplicates = session.execute(
        sa.text(
            """
            SELECT COUNT(*), COALESCE(SUM(CASE WHEN n > 1 THEN n - 1 ELSE 0 END), 0)
            FROM (
                SELECT product_id, run_id, COUNT(*) AS n
                FROM fact_price_snapshot
                GROUP BY product_id, run_id
            ) t
            """
        )
    ).one()
    return RuleOutcome(
        rule_code="DQ006",
        rule_name="One snapshot per product per run",
        dimension=DIMENSION_UNIQUENESS,
        severity=SEVERITY_CRITICAL,
        status="pass" if not duplicates else "fail",
        observed_value=float(duplicates),
        expected_value=0.0,
        threshold=0.0,
        records_checked=int(total),
        records_failed=int(duplicates),
        message="fact_price_snapshot grain violated" if duplicates else "snapshot grain respected",
    )


def _freshness(session: Session, ctx: dict[str, Any]) -> RuleOutcome:
    latest = session.execute(sa.text("SELECT MAX(captured_at) FROM fact_price_snapshot")).scalar()
    if latest is None:
        return RuleOutcome(
            rule_code="DQ007",
            rule_name="Data freshness",
            dimension=DIMENSION_TIMELINESS,
            severity=SEVERITY_WARN,
            status="warn",
            message="no snapshots yet - pipeline has not produced data",
            observed_value=None,
            expected_value=48.0,
            threshold=48.0,
        )
    now = dt.datetime.now(dt.timezone.utc)
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=dt.timezone.utc)
    hours = round((now - latest).total_seconds() / 3600, 3)
    status = "pass" if hours <= 24 else ("warn" if hours <= 48 else "fail")
    return RuleOutcome(
        rule_code="DQ007",
        rule_name="Data freshness (hours since last snapshot)",
        dimension=DIMENSION_TIMELINESS,
        severity=SEVERITY_WARN,
        status=status,
        observed_value=hours,
        expected_value=48.0,
        threshold=48.0,
        message=f"newest snapshot is {hours}h old",
        evidence={"latest": str(latest)},
    )


def _category_coverage(session: Session, ctx: dict[str, Any]) -> RuleOutcome:
    total, uncategorised = session.execute(
        sa.text(
            """
            SELECT COUNT(*),
                   COALESCE(SUM(CASE WHEN c.slug = 'uncategorised' THEN 1 ELSE 0 END), 0)
            FROM dim_product p
            LEFT JOIN dim_category c ON c.category_id = p.category_id
            WHERE p.is_active = 1
            """
        )
    ).one()
    rate = 100.0 if total == 0 else (1 - uncategorised / total) * 100
    return RuleOutcome(
        rule_code="DQ008",
        rule_name="Category coverage",
        dimension=DIMENSION_COMPLETENESS,
        severity=SEVERITY_WARN,
        status=_status(rate, 90.0),
        observed_value=round(rate, 4),
        expected_value=90.0,
        threshold=90.0,
        records_checked=int(total),
        records_failed=int(uncategorised),
        message=f"{uncategorised} products fall back to 'Uncategorised'",
    )


def _price_volatility(session: Session, ctx: dict[str, Any]) -> RuleOutcome:
    """Accuracy guard: flag implausible single-step price jumps (>50%)."""
    total, outliers = session.execute(
        sa.text(
            """
            SELECT COUNT(*),
                   COALESCE(SUM(CASE WHEN ABS(price_change_pct) > 50 THEN 1 ELSE 0 END), 0)
            FROM fact_price_snapshot
            """
        )
    ).one()
    rate = 100.0 if total == 0 else (1 - outliers / total) * 100
    return RuleOutcome(
        rule_code="DQ009",
        rule_name="Price movement plausibility",
        dimension=DIMENSION_ACCURACY,
        severity=SEVERITY_WARN,
        status=_status(rate, 99.0),
        observed_value=round(rate, 4),
        expected_value=99.0,
        threshold=99.0,
        records_checked=int(total),
        records_failed=int(outliers),
        message=f"{outliers} single-step price movements exceed +/-50% (possible scraping defect)",
    )


def _availability_coverage(session: Session, ctx: dict[str, Any]) -> RuleOutcome:
    total, unknown = session.execute(
        sa.text(
            """
            SELECT COUNT(*),
                   COALESCE(SUM(CASE WHEN availability IS NULL OR availability = 'unknown'
                                     THEN 1 ELSE 0 END), 0)
            FROM fact_price_snapshot
            """
        )
    ).one()
    rate = 100.0 if total == 0 else (1 - unknown / total) * 100
    return RuleOutcome(
        rule_code="DQ010",
        rule_name="Availability captured",
        dimension=DIMENSION_COMPLETENESS,
        severity=SEVERITY_INFO,
        status=_status(rate, 85.0),
        observed_value=round(rate, 4),
        expected_value=85.0,
        threshold=85.0,
        records_checked=int(total),
        records_failed=int(unknown),
        message=f"{unknown} snapshots have an unknown availability state",
    )


def _run_completed(session: Session, ctx: dict[str, Any]) -> RuleOutcome:
    """The run must have inserted at least one snapshot."""
    run_id = ctx.get("run_id")
    count = session.execute(
        sa.text("SELECT COUNT(*) FROM fact_price_snapshot WHERE run_id = :run_id"),
        {"run_id": run_id},
    ).scalar() or 0
    return RuleOutcome(
        rule_code="DQ011",
        rule_name="Run produced observations",
        dimension=DIMENSION_COMPLETENESS,
        severity=SEVERITY_CRITICAL,
        status="pass" if count else "fail",
        observed_value=float(count),
        expected_value=1.0,
        threshold=1.0,
        records_checked=int(count),
        records_failed=0 if count else 1,
        message=f"{count} snapshots recorded for run {run_id}",
    )


def _rejected_ratio(session: Session, ctx: dict[str, Any]) -> RuleOutcome:
    run_id = ctx.get("run_id")
    row = session.execute(
        sa.text(
            """
            SELECT COUNT(*), COALESCE(SUM(CASE WHEN is_valid = 0 THEN 1 ELSE 0 END), 0)
            FROM stg_raw_observation WHERE run_id = :run_id
            """,
        ),
        {"run_id": run_id},
    ).one()
    total, rejected = int(row[0]), int(row[1])
    rate = 100.0 if total == 0 else (1 - rejected / total) * 100
    return RuleOutcome(
        rule_code="DQ012",
        rule_name="Rejection rate in staging zone",
        dimension=DIMENSION_VALIDITY,
        severity=SEVERITY_WARN,
        status=_status(rate, 90.0),
        observed_value=round(rate, 4),
        expected_value=90.0,
        threshold=90.0,
        records_checked=total,
        records_failed=rejected,
        message=f"{rejected} of {total} staged records rejected during cleaning",
    )


RULES: tuple[Rule, ...] = (
    Rule("DQ001", "Required fields populated", DIMENSION_COMPLETENESS, SEVERITY_ERROR,
         "Name, price and category must be present for every active product.",
         _completeness),
    Rule("DQ002", "Prices within valid range", DIMENSION_VALIDITY, SEVERITY_ERROR,
         "A parsed price must be >= 0 and <= 1,000,000.", _valid_price),
    Rule("DQ003", "Ratings within 0-5 scale", DIMENSION_VALIDITY, SEVERITY_ERROR,
         "Ratings are rescaled to 0-5 and must land inside that range.", _valid_rating),
    Rule("DQ004", "Currency codes known", DIMENSION_CONSISTENCY, SEVERITY_ERROR,
         "Every snapshot currency must exist in dim_currency.", _currency_known),
    Rule("DQ005", "Product fingerprints unique", DIMENSION_UNIQUENESS, SEVERITY_WARN,
         "Fingerprint collisions mean the deduplicator missed a duplicate.", _uniqueness_fingerprint),
    Rule("DQ006", "One snapshot per product per run", DIMENSION_UNIQUENESS, SEVERITY_CRITICAL,
         "The fact table grain is one row per product per run.", _unique_snapshot_grain),
    Rule("DQ007", "Data freshness", DIMENSION_TIMELINESS, SEVERITY_WARN,
         "At least one snapshot must exist and be younger than 48 hours.", _freshness),
    Rule("DQ008", "Category coverage", DIMENSION_COMPLETENESS, SEVERITY_WARN,
         "At least 90% of products must map to a real category.", _category_coverage),
    Rule("DQ009", "Price movement plausibility", DIMENSION_ACCURACY, SEVERITY_WARN,
         "Single-step price movement above 50% is suspicious.", _price_volatility),
    Rule("DQ010", "Availability captured", DIMENSION_COMPLETENESS, SEVERITY_INFO,
         "Availability should be known for at least 85% of snapshots.", _availability_coverage),
    Rule("DQ011", "Run produced observations", DIMENSION_COMPLETENESS, SEVERITY_CRITICAL,
         "A successful run must persist at least one price snapshot.", _run_completed),
    Rule("DQ012", "Rejection rate in staging zone", DIMENSION_VALIDITY, SEVERITY_WARN,
         "Fewer than 10% of staged records may be rejected.", _rejected_ratio),
)

RULES_BY_CODE: dict[str, Rule] = {rule.code: rule for rule in RULES}


# --------------------------------------------------------------------------------------
# Framework entry point
# --------------------------------------------------------------------------------------
def evaluate_quality(
    session: Session,
    run_id: str,
    *,
    only: list[str] | None = None,
) -> QualityReport:
    """Run every rule (or a subset) and persist the outcomes."""
    import time

    started = time.perf_counter()
    report = QualityReport(run_id=run_id)
    context = {"run_id": run_id}

    for rule in RULES:
        if only and rule.code not in only:
            continue
        outcome = rule.run(session, context)
        report.outcomes.append(outcome)
        session.add(
            DqRuleResult(
                run_id=run_id,
                rule_code=outcome.rule_code,
                rule_name=outcome.rule_name,
                dimension=outcome.dimension,
                severity=outcome.severity,
                status=outcome.status,
                table_name=outcome.evidence.get("table"),
                observed_value=outcome.observed_value,
                expected_value=outcome.expected_value,
                threshold=outcome.threshold,
                records_checked=outcome.records_checked,
                records_failed=outcome.records_failed,
                pass_rate_pct=outcome.pass_rate_pct,
                message=outcome.message,
                evidence=outcome.evidence or None,
                evaluated_at=dt.datetime.now(dt.timezone.utc),
            )
        )
    session.flush()

    report.duration_ms = round((time.perf_counter() - started) * 1000, 2)
    log.info(
        "quality run=%s pass=%d warn=%d fail=%d score=%s",
        run_id, report.passed, report.warned, report.failed, report.score,
    )
    return report


def latest_report(session: Session, run_id: str | None = None) -> dict[str, Any]:
    """Fetch a persisted report without re-evaluating the rules."""
    stmt = sa.select(DqRuleResult).order_by(DqRuleResult.evaluated_at.desc())
    if run_id:
        stmt = stmt.where(DqRuleResult.run_id == run_id)
    rows = list(session.execute(stmt.limit(50)).scalars())
    if not rows:
        return {"run_id": run_id, "total": 0, "pass": 0, "warn": 0, "fail": 0, "score": 100.0, "rules": []}
    run = rows[0].run_id
    rows = [row for row in rows if row.run_id == run]
    total_weight = 0.0
    weighted = 0.0
    for row in rows:
        weight = 1 + _SEVERITY_ORDER.get(row.severity, 1) * 0.5
        total_weight += weight
        weighted += weight * {"pass": 1.0, "warn": 0.75, "fail": 0.0}.get(row.status, 0.0)
    return {
        "run_id": run,
        "total": len(rows),
        "pass": sum(1 for r in rows if r.status == "pass"),
        "warn": sum(1 for r in rows if r.status == "warn"),
        "fail": sum(1 for r in rows if r.status == "fail"),
        "score": round((weighted / total_weight) * 100, 2) if total_weight else 100.0,
        "evaluated_at": rows[0].evaluated_at,
        "rules": [
            {
                "code": r.rule_code,
                "name": r.rule_name,
                "dimension": r.dimension,
                "severity": r.severity,
                "status": r.status,
                "observed_value": r.observed_value,
                "expected_value": r.expected_value,
                "records_checked": r.records_checked,
                "records_failed": r.records_failed,
                "pass_rate_pct": r.pass_rate_pct,
                "message": r.message,
            }
            for r in rows
        ],
    }


def rules_catalog() -> list[dict[str, Any]]:
    """Static catalogue used by the dashboard's DQ screen."""
    return [dataclasses.asdict(rule) | {"evaluator": None} for rule in RULES]


__all__ = [
    "Rule",
    "RuleOutcome",
    "QualityReport",
    "RULES",
    "RULES_BY_CODE",
    "evaluate_quality",
    "latest_report",
    "rules_catalog",
]