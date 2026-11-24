"""A successful run must not look like a failure in the dashboard.

The dashboard's Pipeline health card paints ``error_message`` in warning
colours. Before the fix under test, every source warning - including a single
transient ticker timeout - was copied into that field, so a green "success"
run still displayed a scary orange ConnectError. Warnings have their own
column; this module pins the boundary between the two.
"""

from __future__ import annotations

from app.etl.pipeline import headline_error_message


def test_success_with_transient_source_warning_has_no_error_message():
    warnings = [
        "trading pairs: request failed: ConnectError: [Errno 104] Connection reset by peer",
        "ticker btcusd: unexpected response shape",
    ]
    assert headline_error_message("success", [], [], warnings) is None


def test_blocking_quality_failure_is_the_error_message():
    assert headline_error_message("failed", ["DQ_CRITICAL_NULLS"], [], ["some warning"]) == "DQ_CRITICAL_NULLS"


def test_partial_run_reports_only_the_failed_sources():
    warnings = [
        "bitstamp_tickers: request failed: ConnectError",
        "steam_store: 3 rows rejected by validation",
        "trading pairs: a warning from a source that still succeeded",
    ]
    message = headline_error_message("partial", [], ["bitstamp_tickers"], warnings)
    assert message == "bitstamp_tickers: request failed: ConnectError"
    assert "steam_store" not in (message or "")
    assert "trading pairs" not in (message or "")


def test_failed_run_without_blocking_rules_keeps_no_error_message():
    # Status can be 'failed' for reasons recorded elsewhere; do not invent a
    # headline from unrelated warnings.
    assert headline_error_message("failed", [], [], ["unrelated warning"]) is None


def test_error_message_is_bounded():
    long_blocking = ["x" * 5000]
    assert len(headline_error_message("failed", long_blocking, [], []) or "") == 4000
