"""The no-fake audit must pass a real warehouse and reject a synthetic one.

A check that never fails proves nothing, so these tests cover both directions:
the audit accepts a warehouse whose rows all come from a trusted source, and it
rejects a warehouse that holds rows from a synthetic one.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = ROOT / "scripts" / "audit_no_fakes.py"


def _load_audit():
    """Import the audit script by path - it lives in scripts/, not the package."""
    spec = importlib.util.spec_from_file_location("audit_no_fakes", AUDIT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["audit_no_fakes"] = module
    spec.loader.exec_module(module)
    return module


audit_module = _load_audit()


@pytest.fixture()
def warehouse(tmp_path, database):
    """A SQLite warehouse with a source dimension and one product per source."""
    engine = sa.create_engine(f"sqlite:///{tmp_path}/audit.sqlite3")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE dim_source (
                source_code VARCHAR(64) NOT NULL PRIMARY KEY,
                data_trust VARCHAR(16) NOT NULL
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE dim_product (
                product_id INTEGER NOT NULL PRIMARY KEY,
                source_code VARCHAR(64)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE fact_price_snapshot (
                snapshot_id INTEGER NOT NULL PRIMARY KEY,
                source_code VARCHAR(64)
            )
            """
        )
    return f"sqlite:///{tmp_path}/audit.sqlite3"


def _insert(warehouse_url, source_code, trust, products=3):
    engine = sa.create_engine(warehouse_url)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO dim_source (source_code, data_trust) VALUES (:code, :trust)",
            {"code": source_code, "trust": trust},
        )
        for index in range(products):
            conn.exec_driver_sql(
                "INSERT INTO dim_product (product_id, source_code) VALUES (:id, :code)",
                {"id": index, "code": source_code},
            )
            conn.exec_driver_sql(
                "INSERT INTO fact_price_snapshot (snapshot_id, source_code) VALUES (:id, :code)",
                {"id": index, "code": source_code},
            )
    engine.dispose()


def test_a_warehouse_of_real_sources_is_clean(warehouse):
    _insert(warehouse, "openlibrary_books", "real")
    report = audit_module.audit(warehouse)
    assert report["clean"] is True
    assert report["findings"] == []
    # Three products and three snapshots, both counted.
    assert report["rows_audited"] == 6


def test_a_synthetic_source_is_reported(warehouse):
    _insert(warehouse, "local_demo", "synthetic")
    report = audit_module.audit(warehouse)
    assert report["clean"] is False
    tables = {finding["table"] for finding in report["findings"]}
    assert {"dim_product", "fact_price_snapshot"} <= tables
    assert all("synthetic" in finding["reason"] for finding in report["findings"])


def test_a_sandbox_source_is_rejected_unless_it_is_allowed(warehouse):
    _insert(warehouse, "books_to_scrape", "sandbox")
    assert audit_module.audit(warehouse)["clean"] is False
    allowed = audit_module.audit(warehouse, allow_sandbox=True)
    assert allowed["clean"] is True


def test_a_row_from_an_unregistered_source_is_not_verifiable(warehouse):
    # The source is written into the fact table but never registered, so the
    # row cannot be attributed to anything.
    engine = sa.create_engine(warehouse)
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO dim_product (product_id, source_code) VALUES (1, 'mystery_source')")
    engine.dispose()
    report = audit_module.audit(warehouse)
    assert report["clean"] is False
    assert any("not registered" in finding["reason"] for finding in report["findings"])


def test_the_synthetic_namespace_is_reported(warehouse):
    _insert(warehouse, "openlibrary_books", "real")
    engine = sa.create_engine(warehouse)
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO dim_product (product_id, source_code) VALUES (99, 'SYN-0001')")
    engine.dispose()
    report = audit_module.audit(warehouse)
    assert report["clean"] is False
    assert any("SYN-" in finding["source_code"] for finding in report["findings"])
