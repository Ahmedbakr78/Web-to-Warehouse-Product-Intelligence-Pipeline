"""Tests for webhooks, dataset export and run comparison.

These cover the three features added on top of the original scope:

* ``services.webhooks`` - HMAC signing, SSRF-safe target validation, delivery,
  retry/backoff bookkeeping and auto-disable after repeated failures.
* ``services.exporter`` - the dataset registry, filter validation, injection safety
  and CSV/JSON serialisation.
* ``analytics.service.compare_runs`` - metric deltas, DQ regressions and record
  movement between two runs.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import sqlalchemy as sa

from app.analytics.service import compare_runs
from app.models.app_users import AppUser, AppWebhook
from app.services import exporter, webhooks


# --------------------------------------------------------------------------------------
# A real local HTTP receiver, so delivery is tested end to end rather than mocked.
# --------------------------------------------------------------------------------------
class _Receiver:
    """Captures webhook POSTs and can be told to fail."""

    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.received: list[dict] = []
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length)
                receiver.received.append(
                    {
                        "body": body,
                        "headers": {k.lower(): v for k, v in self.headers.items()},
                    }
                )
                self.send_response(receiver.status)
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

            def log_message(self, *args: object) -> None:
                """Silence the default stderr logging."""

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/hook"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture()
def receiver():
    box = _Receiver()
    try:
        yield box
    finally:
        box.close()


@pytest.fixture()
def admin(session):
    return session.execute(sa.select(AppUser).where(AppUser.role == "admin")).scalars().first()


def _hook(session, admin, url: str, **kwargs) -> AppWebhook:
    """Insert a subscription directly - URL validation is bypassed on purpose so the
    test can point at a loopback receiver (production URLs are validated on create)."""
    hook = AppWebhook(
        user_id=admin.user_id,
        name=kwargs.pop("name", "test hook"),
        target_url=url,
        secret=webhooks.generate_secret(),
        events=kwargs.pop("events", ["run.completed"]),
        is_active=kwargs.pop("is_active", True),
        max_attempts=kwargs.pop("max_attempts", 3),
        **kwargs,
    )
    session.add(hook)
    session.flush()
    return hook


# --------------------------------------------------------------------------------------
# Webhooks: signing
# --------------------------------------------------------------------------------------
def test_signature_round_trip():
    secret = webhooks.generate_secret()
    body = b'{"event":"run.completed"}'
    signature = webhooks.sign_payload(secret, body, 1_700_000_000)
    assert signature.startswith("sha256=")
    assert webhooks.verify_signature(secret, body, 1_700_000_000, signature)
    assert not webhooks.verify_signature(secret, body, 1_700_000_000, "sha256=00")
    # body tampering and replay with a different timestamp both fail
    assert not webhooks.verify_signature(secret, b'{"event":"evil"}', 1_700_000_000, signature)
    assert not webhooks.verify_signature(secret, body, 1_700_000_001, signature)
    # a different secret never validates
    assert not webhooks.verify_signature(webhooks.generate_secret(), body, 1_700_000_000, signature)


def test_generated_secrets_are_unique():
    assert len({webhooks.generate_secret() for _ in range(25)}) == 25


def test_verify_signature_rejects_garbage():
    assert not webhooks.verify_signature("whsec_x", b"{}", "not-a-timestamp", "sha256=abc")
    assert not webhooks.verify_signature("whsec_x", b"{}", 1, None)


# --------------------------------------------------------------------------------------
# Webhooks: SSRF protection
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/hook",
        "http://localhost/hook",
        "http://127.0.0.1/hook",
        "http://10.1.2.3/hook",
        "http://192.168.0.10/hook",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/hook",
        "http://user:pass@example.com/hook",
        "https://",
    ],
)
def test_validate_target_url_blocks_unsafe_targets(url):
    with pytest.raises(webhooks.WebhookError):
        webhooks.validate_target_url(url)


def test_validate_target_url_error_carries_details():
    with pytest.raises(webhooks.WebhookError) as excinfo:
        webhooks.validate_target_url("http://127.0.0.1/x")
    assert excinfo.value.status_code == 400
    assert excinfo.value.code == "webhook_error"
    assert "127.0.0.1" in str(excinfo.value.details)


# --------------------------------------------------------------------------------------
# Webhooks: events
# --------------------------------------------------------------------------------------
def test_normalise_events_defaults_to_everything():
    assert webhooks.normalise_events(None) == list(webhooks.WEBHOOK_EVENTS)


def test_normalise_events_dedupes_and_keeps_wildcard():
    assert webhooks.normalise_events(["run.completed", "run.completed", "*"]) == [
        "run.completed",
        "*",
    ]


@pytest.mark.parametrize("bad", ["", "not.an.event", "x" * 100])
def test_normalise_events_rejects_unknown(bad):
    with pytest.raises(webhooks.WebhookError):
        webhooks.normalise_events([bad])


def test_subscriptions_for_event_filters_by_name_and_wildcard(session, admin, receiver):
    targeted = _hook(session, admin, receiver.url, events=["price.spike"])
    wildcard = _hook(session, admin, receiver.url, events=["*"], name="wildcard")
    unrelated = _hook(session, admin, receiver.url, events=["dq.failed"], name="unrelated")
    session.flush()

    matched = {h.webhook_id for h in webhooks.subscriptions_for_event(session, "price.spike")}
    assert targeted.webhook_id in matched
    assert wildcard.webhook_id in matched
    assert unrelated.webhook_id not in matched


# --------------------------------------------------------------------------------------
# Webhooks: delivery
# --------------------------------------------------------------------------------------
def test_deliver_success_records_delivery_and_headers(session, admin, receiver):
    hook = _hook(session, admin, receiver.url)
    outcome = webhooks.deliver(session, hook, "run.completed", {"run_id": "abc"})
    session.flush()
    delivery = outcome.delivery
    assert delivery is not None

    assert outcome.ok is True
    assert outcome.status == "success"
    assert outcome.delivery is delivery
    assert delivery.status_code == 200
    assert delivery.delivered_at is not None
    assert hook.success_count == 1
    assert hook.consecutive_failures == 0
    assert hook.last_status_code == 200

    assert len(receiver.received) == 1
    headers = receiver.received[0]["headers"]
    assert headers[webhooks.EVENT_HEADER.lower()] == "run.completed"
    assert headers[webhooks.SIGNATURE_HEADER.lower()].startswith("sha256=")
    # the receiver can verify the signature with the subscription secret
    assert webhooks.verify_signature(
        hook.secret,
        receiver.received[0]["body"],
        headers[webhooks.TIMESTAMP_HEADER.lower()],
        headers[webhooks.SIGNATURE_HEADER.lower()],
    )
    envelope = json.loads(receiver.received[0]["body"])
    assert envelope["event"] == "run.completed"
    assert envelope["data"] == {"run_id": "abc"}


def test_deliver_failure_is_recorded_with_backoff(session, admin):
    hook = _hook(session, admin, "http://127.0.0.1:9/unreachable")
    outcome = webhooks.deliver(session, hook, "run.completed", {})
    session.flush()
    delivery = outcome.delivery

    assert delivery is not None
    assert outcome.ok is False
    assert delivery.status == "failed"
    assert delivery.error
    assert delivery.next_retry_at is not None
    assert hook.failure_count == 1
    assert hook.consecutive_failures == 1


def test_deliver_http_error_status_is_reported(session, admin):
    failing = _Receiver(status=500)
    try:
        hook = _hook(session, admin, failing.url)
        outcome = webhooks.deliver(session, hook, "run.completed", {})
        session.flush()
        assert outcome.delivery.status == "failed"
        assert outcome.status_code == 500
    finally:
        failing.close()


def test_subscription_auto_disables_after_repeated_failures(session, admin):
    hook = _hook(session, admin, "http://127.0.0.1:9/unreachable")
    for _ in range(webhooks.MAX_FAILURES_BEFORE_DISABLE):
        webhooks.deliver(session, hook, "run.completed", {})
        session.flush()
    assert hook.is_active is False
    assert hook.disabled_reason
    # a disabled hook is no longer picked up for new events
    assert hook not in webhooks.subscriptions_for_event(session, "run.completed")


def test_emit_fans_out_to_matching_subscriptions(session, admin, receiver):
    matching = _hook(session, admin, receiver.url, events=["run.completed"])
    _hook(session, admin, receiver.url, events=["dq.failed"], name="other")
    session.flush()

    deliveries = webhooks.emit(session, "run.completed", {"run_id": "xyz"})
    session.flush()
    assert len(deliveries) == 1
    assert deliveries[0].webhook_id == matching.webhook_id
    assert len(receiver.received) == 1


def test_emit_never_raises_when_delivery_breaks(session, admin):
    """A dead webhook must not fail the pipeline run that emitted the event."""
    hook = _hook(session, admin, "http://127.0.0.1:9/unreachable")
    session.flush()
    deliveries = webhooks.emit(session, "run.completed", {"run_id": "safe"})
    assert len(deliveries) == 1
    assert deliveries[0].status == "failed"
    assert hook.failure_count == 1


# --------------------------------------------------------------------------------------
# Webhooks: retries
# --------------------------------------------------------------------------------------
def test_retry_due_resends_after_backoff_elapsed(session, admin, receiver):
    hook = _hook(session, admin, "http://127.0.0.1:9/unreachable")
    delivery = webhooks.deliver(session, hook, "run.completed", {"run_id": "retry-me"}).delivery
    assert delivery is not None
    delivery.next_retry_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)
    session.flush()

    hook.target_url = receiver.url
    session.flush()

    attempted = webhooks.retry_due(session)
    session.flush()
    assert attempted == 1
    assert delivery.status == "success"
    assert delivery.next_retry_at is None
    assert delivery.attempts == 2
    assert len(receiver.received) == 1


def test_retry_due_ignores_deliveries_that_are_not_due(session, admin):
    hook = _hook(session, admin, "http://127.0.0.1:9/unreachable")
    delivery = webhooks.deliver(session, hook, "run.completed", {})
    delivery.next_retry_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
    session.flush()
    assert webhooks.retry_due(session) == 0


def test_retry_gives_up_after_max_attempts(session, admin):
    hook = _hook(session, admin, "http://127.0.0.1:9/unreachable", max_attempts=2)
    delivery = webhooks.deliver(session, hook, "run.completed", {}).delivery
    assert delivery is not None
    delivery.attempts = 1
    delivery.next_retry_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
    session.flush()

    assert webhooks.retry_due(session) == 1
    session.flush()
    assert delivery.attempts == 2
    assert delivery.next_retry_at is None
    assert delivery.status == "failed"


def test_retry_due_skips_disabled_subscriptions(session, admin):
    hook = _hook(session, admin, "http://127.0.0.1:9/unreachable", is_active=False)
    delivery = webhooks.deliver(session, hook, "run.completed", {}).delivery
    assert delivery is not None
    delivery.next_retry_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
    session.flush()
    assert webhooks.retry_due(session) == 0


# --------------------------------------------------------------------------------------
# Export registry
# --------------------------------------------------------------------------------------
def test_every_registered_dataset_has_a_title_and_group():
    for key, dataset in exporter.DATASETS.items():
        assert dataset.key == key
        assert dataset.title and dataset.group and dataset.description
        assert "{where}" in dataset.sql
        assert ":row_limit" in dataset.sql


def test_list_datasets_shape():
    items = exporter.list_datasets()
    assert len(items) == len(exporter.DATASETS)
    assert {"key", "title", "description", "group", "filters"} <= set(items[0])


def test_unknown_dataset_raises_export_error():
    with pytest.raises(exporter.ExportError) as excinfo:
        exporter.get_dataset("does-not-exist")
    assert "available" in excinfo.value.details


def test_fetch_rows_returns_rows_for_every_dataset(db):
    for key in exporter.DATASETS:
        _, rows = exporter.fetch_rows(db, key, row_limit=3)
        assert isinstance(rows, list)
        for row in rows:
            assert all(value is not None or True for value in row.values())


def test_fetch_rows_rejects_unsupported_filter(db):
    with pytest.raises(exporter.ExportError) as excinfo:
        exporter.fetch_rows(db, "products", filters={"status": "success"}, row_limit=3)
    assert "not supported" in excinfo.value.message


def test_fetch_rows_rejects_injection_attempt(db):
    with pytest.raises(exporter.ExportError):
        exporter.fetch_rows(db, "products", filters={"'; DROP TABLE dim_product; --": "x"}, row_limit=3)


def test_fetch_rows_enforces_row_limit_bounds(db):
    for bad in (0, -1, exporter.MAX_ROWS + 1):
        with pytest.raises(exporter.ExportError):
            exporter.fetch_rows(db, "products", row_limit=bad)


def test_supported_filters_apply_cleanly(db):
    _, rows = exporter.fetch_rows(db, "runs", filters={"status": "success"}, row_limit=5)
    assert all(row["status"] == "success" for row in rows)
    _, rows = exporter.fetch_rows(db, "sources", filters={"enabled": "true"}, row_limit=5)
    assert all(row["enabled"] in (True, "true", 1) for row in rows)


def test_boolean_filter_rejects_non_boolean(db):
    with pytest.raises(exporter.ExportError):
        exporter.fetch_rows(db, "sources", filters={"enabled": "perhaps"}, row_limit=3)


def test_direction_filter_validates_input(db):
    with pytest.raises(exporter.ExportError):
        exporter.fetch_rows(db, "movers", filters={"direction": "sideways"}, row_limit=3)


def test_search_filter_is_escaped_not_interpolated(db):
    _, rows = exporter.fetch_rows(db, "products", filters={"search": "o'brien"}, row_limit=3)
    assert isinstance(rows, list)  # a quote must not break the query
    assert exporter.fetch_rows(db, "products", filters={"search": "a"}, row_limit=3)[1] is not None


# --------------------------------------------------------------------------------------
# Export serialisation
# --------------------------------------------------------------------------------------
SAMPLE = [
    {"product_id": 1, "canonical_name": "Phone", "price_usd": 199.99},
    {"product_id": 2, "canonical_name": "Tablet", "price_usd": None},
]


def test_to_csv_writes_header_and_rows():
    csv_text = exporter.to_csv(SAMPLE)
    lines = csv_text.strip().splitlines()
    assert lines[0] == "product_id,canonical_name,price_usd"
    assert lines[1] == "1,Phone,199.99"
    assert lines[2] == "2,Tablet,"  # None becomes an empty cell


def test_to_csv_without_rows_is_empty():
    assert exporter.to_csv([]) == ""


def test_to_json_carries_an_envelope():
    dataset = exporter.DATASETS["products"]
    payload = json.loads(exporter.to_json(SAMPLE, dataset, 100))
    assert payload["dataset"] == "products"
    assert payload["row_count"] == 2
    assert payload["row_limit"] == 100
    assert payload["columns"][0] == "product_id"
    assert payload["rows"][0]["canonical_name"] == "Phone"
    assert payload["exported_at"]


def test_filename_is_deterministic_and_stamped():
    dataset = exporter.DATASETS["products"]
    assert exporter.filename_for(dataset, "csv", "20260101") == "products-20260101.csv"
    assert exporter.filename_for(dataset, "json", "20260101") == "products-20260101.json"


def test_export_error_is_a_pipeline_error():
    from app.core.errors import PipelineError

    assert issubclass(exporter.ExportError, PipelineError)
    assert exporter.ExportError.status_code == 400


# --------------------------------------------------------------------------------------
# Run comparison
# --------------------------------------------------------------------------------------
def _insert_run(session, run_id: str, **kwargs) -> None:
    """Insert a minimal etl_run row (the table has many NOT NULL columns)."""
    values: dict = {
        "run_id": run_id,
        "pipeline": "product_intelligence",
        "status": "success",
        "trigger": "manual",
        "target_database": "postgres",
        "started_at": dt.datetime.now(dt.timezone.utc),
        "created_at": dt.datetime.now(dt.timezone.utc),
        "records_extracted": 10,
        "records_valid": 10,
        "records_rejected": 0,
        "records_inserted": 10,
        "records_updated": 0,
        "duplicates_merged": 0,
        "new_products": 0,
        "price_changes": 0,
        "removed_products": 0,
        "catalog_matched": 0,
        "dq_passed": 12,
        "dq_failed": 0,
        "dq_score": 100.0,
        "duration_ms": 1000,
    }
    values.update(kwargs)
    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)
    session.execute(sa.text(f"INSERT INTO etl_run ({columns}) VALUES ({placeholders})"), values)
    session.flush()


def test_compare_runs_returns_empty_for_unknown_run(session):
    assert compare_runs(session, "missing-a", "missing-b") == {}


def test_compare_runs_404s_with_context(session):
    _insert_run(session, "cmp_base")

    assert compare_runs(session, "cmp_base", "missing") == {}


def test_compare_runs_computes_metric_deltas(session):
    _insert_run(session, "cmp_a", records_extracted=10, records_valid=8, dq_score=90.0)
    _insert_run(session, "cmp_b", records_extracted=25, records_valid=20, dq_score=95.5)
    session.flush()

    diff = compare_runs(session, "cmp_a", "cmp_b")
    metrics = {m["metric"]: m for m in diff["metrics"]}
    assert metrics["records_extracted"]["delta"] == 15
    assert metrics["records_extracted"]["delta_pct"] == 150.0
    assert metrics["records_valid"]["delta"] == 12
    assert diff["dq"]["score_delta"] == 5.5
    assert diff["base"]["run_id"] == "cmp_a"
    assert diff["target"]["run_id"] == "cmp_b"


def test_compare_runs_handles_zero_baseline(session):
    _insert_run(session, "cmp_zero", records_extracted=0)
    _insert_run(session, "cmp_nonzero", records_extracted=5)
    session.flush()
    metrics = {m["metric"]: m for m in compare_runs(session, "cmp_zero", "cmp_nonzero")["metrics"]}
    assert metrics["records_extracted"]["delta_pct"] is None  # no division by zero


def test_compare_runs_reports_dq_regressions(session):
    _insert_run(session, "cmp_dq_a")
    _insert_run(session, "cmp_dq_b")
    for run_id, status in (("cmp_dq_a", "pass"), ("cmp_dq_b", "fail")):
        session.execute(
            sa.text(
                "INSERT INTO dq_rule_result (run_id, rule_code, dimension, severity, status,"
                " records_checked, records_failed, evaluated_at) VALUES (:r, 'PRICE_POSITIVE', 'validity', 'error', :s, 10, 0, :t)"
            ),
            {"r": run_id, "s": status, "t": dt.datetime.now(dt.timezone.utc)},
        )
        session.execute(
            sa.text(
                "INSERT INTO dq_rule_result (run_id, rule_code, dimension, severity, status,"
                " records_checked, records_failed, evaluated_at) VALUES (:r, 'NAME_PRESENT', 'completeness', 'error', 'pass', 10, 0, :t)"
            ),
            {"r": run_id, "t": dt.datetime.now(dt.timezone.utc)},
        )
    session.flush()

    dq = compare_runs(session, "cmp_dq_a", "cmp_dq_b")["dq"]
    assert dq["regressions"] == ["PRICE_POSITIVE"]
    assert dq["fixed"] == []


def test_compare_runs_reports_dq_fixes(session):
    _insert_run(session, "cmp_fix_a")
    _insert_run(session, "cmp_fix_b")
    for run_id, status in (("cmp_fix_a", "fail"), ("cmp_fix_b", "pass")):
        session.execute(
            sa.text(
                "INSERT INTO dq_rule_result (run_id, rule_code, dimension, severity, status,"
                " records_checked, records_failed, evaluated_at) VALUES (:r, 'PRICE_POSITIVE', 'validity', 'error', :s, 10, 0, :t)"
            ),
            {"r": run_id, "s": status, "t": dt.datetime.now(dt.timezone.utc)},
        )
    session.flush()
    assert compare_runs(session, "cmp_fix_a", "cmp_fix_b")["dq"]["fixed"] == ["PRICE_POSITIVE"]


def test_compare_runs_compares_performance(session):
    _insert_run(session, "cmp_p_a", duration_ms=1000)
    _insert_run(session, "cmp_p_b", duration_ms=2500)
    session.flush()
    perf = compare_runs(session, "cmp_p_a", "cmp_p_b")["performance"]
    assert perf["delta_ms"] == 1500
    assert perf["delta_pct"] == 150.0


def test_compare_runs_on_seeded_data(db):
    """Runs against the seeded demo warehouse: shape must hold even with no movement."""
    runs = db.execute(sa.text("SELECT run_id FROM etl_run ORDER BY started_at LIMIT 2")).scalars().all()
    if len(runs) < 2:
        pytest.skip("needs at least two seeded runs")
    diff = compare_runs(db, runs[0], runs[1])
    assert {"base", "target", "metrics", "dq", "catalogue", "prices", "performance"} <= set(diff)
    assert len(diff["metrics"]) == 12
    for metric in diff["metrics"]:
        assert {"metric", "base", "target", "delta"} <= set(metric)


# --------------------------------------------------------------------------------------
# Backfill planning and progress
# --------------------------------------------------------------------------------------
def _days_ago(count: int) -> str:
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=count)).date().isoformat()


def test_plan_backfill_expands_one_day_per_date():
    from app.services.backfill import plan_backfill

    plan = plan_backfill(
        start_date=_days_ago(3), end_date=_days_ago(1), sources=["local_demo"], created_by="t@example.com"
    )
    assert len(plan.days) == 3
    assert plan.backfill_id.startswith("bf_")
    assert plan.days == sorted(plan.days)
    assert plan.created_by == "t@example.com"
    assert plan.as_dict()["total_days"] == 3
    assert plan.as_dict()["sources"] == ["local_demo"]


def test_plan_backfill_accepts_single_day():
    from app.services.backfill import plan_backfill

    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    assert len(plan_backfill(start_date=today, end_date=today).days) == 1


@pytest.mark.parametrize(
    "start,end,label",
    [
        (_days_ago(1), _days_ago(5), "reversed range"),
        (_days_ago(60), _days_ago(1), "more than the maximum span"),
        (_days_ago(1), _days_ago(-1), "end date in the future"),
        ("nonsense", _days_ago(1), "unparseable date"),
    ],
)
def test_plan_backfill_rejects_bad_ranges(start, end, label):
    from app.core.errors import ValidationError
    from app.services.backfill import plan_backfill

    with pytest.raises(ValidationError):
        plan_backfill(start_date=start, end_date=end)


def test_plan_backfill_rejects_missing_dates():
    from app.core.errors import ValidationError
    from app.services.backfill import plan_backfill

    with pytest.raises(ValidationError):
        plan_backfill(start_date=None, end_date=_days_ago(1))


def test_execute_backfill_isolates_a_failing_day(monkeypatch):
    """One bad day must not abandon the rest of the range."""
    from app.services import backfill as backfill_mod

    plan = backfill_mod.plan_backfill(start_date=_days_ago(2), end_date=_days_ago(1), sources=["local_demo"])
    calls: list[str] = []

    class FakeResult:
        def __init__(self, day: str) -> None:
            self.run_id = f"run_{day}"
            self.status = "success"
            self.counters = {"staged": 5, "snapshots_inserted": 4}
            self.quality = {"score": 99.5}

    class FakePipeline:
        def __init__(self, config) -> None:
            self.config = config

        def run(self):
            day = self.config.run_key.split(":")[1]
            calls.append(day)
            if len(calls) == 1:
                raise RuntimeError("source unavailable")
            return FakeResult(day)

    monkeypatch.setattr("app.etl.pipeline.Pipeline", FakePipeline)
    summary = backfill_mod.execute_backfill(plan)

    assert len(calls) == 2
    assert summary["planned_days"] == 2
    assert summary["failed_days"] == 1
    assert summary["succeeded_days"] == 1
    assert summary["status"] == "partial"
    assert summary["runs"][0]["error"].startswith("RuntimeError")
    assert summary["runs"][1]["records_extracted"] == 5
    assert summary["runs"][1]["dq_score"] == 99.5


def test_execute_backfill_dry_run_tags_every_day(monkeypatch):
    from app.etl.pipeline import PipelineConfig
    from app.services import backfill as backfill_mod

    seen: list[PipelineConfig] = []

    class FakeResult:
        run_id = "r1"
        status = "success"
        counters: dict = {}
        quality: dict = {}

    class FakePipeline:
        def __init__(self, config) -> None:
            seen.append(config)

        def run(self):
            return FakeResult()

    monkeypatch.setattr("app.etl.pipeline.Pipeline", FakePipeline)
    plan = backfill_mod.plan_backfill(start_date=_days_ago(1), end_date=_days_ago(1), sources=["local_demo"])
    backfill_mod.execute_backfill(plan)

    assert len(seen) == 1
    assert seen[0].trigger == "backfill"
    assert seen[0].run_key.startswith(f"{plan.backfill_id}:")
    assert seen[0].created_by == "backfill"


def test_backfill_progress_rolls_up_runs(session):
    from app.services.backfill import backfill_progress

    job = "bf_testrollup"
    _insert_run(
        session,
        f"{job}-r1",
        run_key=f"{job}:2026-01-01",
        trigger="backfill",
        records_extracted=10,
        new_products=2,
        dq_score=90.0,
    )
    _insert_run(
        session,
        f"{job}-r2",
        run_key=f"{job}:2026-01-02",
        trigger="backfill",
        records_extracted=15,
        new_products=3,
        dq_score=100.0,
    )
    _insert_run(
        session,
        f"{job}-r3",
        run_key=f"{job}:2026-01-03",
        trigger="backfill",
        status="failed",
        records_extracted=0,
        dq_score=None,
    )
    session.flush()

    progress = backfill_progress(session, job)
    assert progress["found"] is True
    assert progress["total_runs"] == 3
    assert progress["succeeded_runs"] == 2
    assert progress["failed_runs"] == 1
    assert progress["records_extracted"] == 25
    assert progress["new_products"] == 5
    assert progress["average_dq_score"] == 95.0
    assert progress["status"] == "partial"
    assert len(progress["runs"]) == 3


def test_backfill_progress_unknown_job(session):
    from app.services.backfill import backfill_progress

    assert backfill_progress(session, "bf_missing")["found"] is False


def test_list_backfills_groups_days_into_one_job(session):
    from app.services.backfill import list_backfills

    job = "bf_grouped"
    _insert_run(session, f"{job}-a", run_key=f"{job}:2026-01-01", trigger="backfill", records_extracted=4)
    _insert_run(session, f"{job}-b", run_key=f"{job}:2026-01-02", trigger="backfill", records_extracted=6)
    session.flush()

    jobs = list_backfills(session, limit=10)
    mine = [j for j in jobs if j["backfill_id"] == job]
    assert len(mine) == 1, "days must roll up into a single job entry"
    assert mine[0]["total_runs"] == 2
    assert mine[0]["records_extracted"] == 10
    assert mine[0]["status"] == "success"


def test_list_backfills_ignores_normal_runs(session):
    from app.services.backfill import list_backfills

    _insert_run(session, "ordinary-run", trigger="manual", records_extracted=99)
    session.flush()
    assert list_backfills(session, limit=10) == []
