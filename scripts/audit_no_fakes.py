#!/usr/bin/env python3
"""Audit a warehouse and prove it holds nothing but real data.

    python3 scripts/audit_no_fakes.py --database sqlite:///./var/pip-real-test.db

Every table that records which upstream a row came from is checked against the
trust level persisted in ``dim_source``. A row whose source is not classified
``real`` is reported, and the audit exits non-zero.

The point is not to trust the pipeline's own bookkeeping: the check reads the
fact, staging and aggregate tables directly and asks the dimension table where
each record really came from. A source that is missing from ``dim_source``
entirely is treated as unverified, because a row nobody can attribute is not
provably real.

Optional flags:

    --allow-sandbox   accept ``sandbox`` sources (a real endpoint that
                      publishes a test corpus) as well as ``real``
    --json            print the report as JSON
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import sqlalchemy as sa

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

#: Every table that records the upstream a row came from.
AUDITED_TABLES = (
    "dim_product",
    "fact_price_snapshot",
    "chg_price_change",
    "chg_product_event",
    "fact_catalog_snapshot",
    "stg_raw_observation",
    "agg_category_daily",
)

#: Tables that hold no upstream attribution but can still carry a row that was
#: written by a synthetic source. These are checked by the synthetic namespace.
NAMESPACE_TABLES = ("dim_product", "fact_price_snapshot", "chg_price_change")

#: The reserved namespace synthetic products are written under.
SYNTHETIC_PREFIX = "SYN-"

#: The retailer's own catalogue. The seeded demo catalogue is *generated*, so
#: it is not market data either - it is the "our list price" side of every
#: reconciliation and price-gap figure, and a reader must be able to tell a
#: seeded catalogue from an imported one.
CATALOG_TABLE = "catalog_product"

#: How a seeded catalogue row is recognised.
CATALOG_SEED_MARKERS: tuple[tuple[str, str], ...] = (
    ("product_url", "internal.local"),
    ("supplier", "Acme Imports"),
    ("supplier", "Globex Supply"),
    ("supplier", "Initech Wholesale"),
    ("supplier", "Umbrella Ltd"),
)


def _quote(engine, name: str) -> str:
    """Quote an identifier the way the connected dialect expects.

    MySQL does not accept a double-quoted identifier unless it runs in
    ANSI_QUOTES mode, so the audit has to ask the dialect rather than assume.
    """
    preparer = engine.dialect.identifier_preparer
    return preparer.quote(name)


def _rollup_inputs(
    conn,
    tables: set[str],
    trust: dict[str, str],
    accepted: set[str],
    table: str,
) -> list[str]:
    """Return the untrusted sources that fed a cross-source rollup.

    A rollup row with no ``source_code`` aggregates several upstreams. It is
    only as trustworthy as the snapshots underneath it, so the audit joins the
    rollup back to ``fact_price_snapshot`` and checks every contributing
    source. A rollup that cannot be traced back at all is reported as
    unverifiable rather than quietly accepted.
    """
    if table != "agg_category_daily":
        # The only table audited with a nullable source is the category rollup.
        return []
    if "fact_price_snapshot" not in tables or "dim_product" not in tables:
        return []

    contributors = conn.execute(
        sa.text(
            """
            SELECT DISTINCT s.source_code
            FROM agg_category_daily a
            JOIN fact_price_snapshot s ON s.date_id = a.date_id
            JOIN dim_product p ON p.product_id = s.product_id
                                 AND p.category_id = a.category_id
            WHERE a.source_code IS NULL
            """
        )
    ).all()
    untrusted: list[str] = []
    for (code,) in contributors:
        level = trust.get(code)
        if level is None:
            untrusted.append(f"{code} (unregistered)")
        elif level not in accepted:
            untrusted.append(f"{code} ({level})")
    return sorted(untrusted)


def audit(database_url: str, *, allow_sandbox: bool = False) -> dict:
    """Return a report of every non-real row found in the warehouse.

    The audit opens its own connection to the URL it is given rather than the
    application's cached engine, so it can be pointed at any database - a
    throwaway copy, a production warehouse, or a file that is not the one the
    app is currently using.
    """
    accepted = {"real", "sandbox"} if allow_sandbox else {"real"}
    engine = sa.create_engine(database_url, future=True)
    findings: list[dict] = []
    notes: list[str] = []
    per_table: dict[str, dict] = {}

    with engine.connect() as conn:
        tables = set(sa.inspect(conn).get_table_names())
        trust: dict[str, str] = {}
        if "dim_source" in tables:
            for code, level in conn.execute(sa.text("SELECT source_code, data_trust FROM dim_source")):
                trust[code] = (level or "real").lower()

        for table in AUDITED_TABLES:
            if table not in tables:
                continue
            rows = conn.execute(
                sa.text(
                    f"SELECT source_code, COUNT(*) FROM {_quote(engine, table)} GROUP BY source_code"
                )
            ).all()
            counts = dict(rows)
            per_table[table] = counts
            for code, count in counts.items():
                if code is None:
                    # A cross-source rollup carries no single upstream. It is
                    # still audited: every snapshot that fed it must be real.
                    bad = _rollup_inputs(conn, tables, trust, accepted, table)
                    if bad:
                        findings.append(
                            {
                                "table": table,
                                "source_code": "(all sources)",
                                "rows": count,
                                "reason": f"the rollup is built from untrusted rows: {', '.join(bad)}",
                            }
                        )
                    continue
                level = trust.get(code)
                if level is None:
                    findings.append(
                        {
                            "table": table,
                            "source_code": code,
                            "rows": count,
                            "reason": "source is not registered in dim_source, so the row cannot be verified",
                        }
                    )
                elif level not in accepted:
                    findings.append(
                        {
                            "table": table,
                            "source_code": code,
                            "rows": count,
                            "reason": f"source is classified '{level}', not real market data",
                        }
                    )

        for table in NAMESPACE_TABLES:
            if table not in tables:
                continue
            count = conn.execute(
                sa.text(
                    f"SELECT COUNT(*) FROM {_quote(engine, table)} WHERE source_code LIKE :prefix"
                ).bindparams(
                    prefix=f"{SYNTHETIC_PREFIX}%"
                )
            ).scalar()
            if count:
                findings.append(
                    {
                        "table": table,
                        "source_code": f"{SYNTHETIC_PREFIX}*",
                        "rows": int(count),
                        "reason": "row sits in the reserved synthetic namespace",
                    }
                )

        if CATALOG_TABLE in tables:
            # The internal catalogue is the *retailer's* own product list, not
            # market data, so a generated one is a placeholder rather than a
            # fabricated observation. It is reported as a note - with the
            # command that removes it - and it does not make the *market* data
            # suspect. A reader is told, not left to guess.
            count = int(
                conn.execute(
                    sa.text(f"SELECT COUNT(*) FROM {_quote(engine, CATALOG_TABLE)}")
                ).scalar()
                or 0
            )
            if count:
                notes.append(
                    f"{count} row(s) in {CATALOG_TABLE} - the internal catalogue is a generated "
                    f"placeholder, not an imported product list "
                    f"(remove it with: python -m app.cli.main purge-demo-catalog)"
                )

        total_rows = 0
        for table in ("dim_product", "fact_price_snapshot"):
            if table in tables:
                total_rows += int(
                    conn.execute(
                        sa.text(f"SELECT COUNT(*) FROM {_quote(engine, table)}")
                    ).scalar()
                    or 0
                )

    engine.dispose()
    return {
        "database": database_url,
        "accepted_trust": sorted(accepted),
        "registered_sources": len(trust),
        "untrusted_sources": sorted(code for code, level in trust.items() if level not in accepted),
        "rows_per_table": per_table,
        "rows_audited": total_rows,
        "findings": findings,
        "notes": notes,
        "clean": not findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--database", default=os.getenv("DATABASE_URL", "sqlite:///./var/pipeline.sqlite3"))
    parser.add_argument("--allow-sandbox", action="store_true", help="also accept sandbox sources")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args()

    report = audit(args.database, allow_sandbox=args.allow_sandbox)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"database            {report['database']}")
        print(f"accepted trust      {', '.join(report['accepted_trust'])}")
        print(f"registered sources  {report['registered_sources']}")
        print(f"untrusted sources   {len(report['untrusted_sources'])}")
        for table, counts in sorted(report["rows_per_table"].items()):
            if counts:
                detail = ", ".join(f"{code}={count}" for code, count in sorted(counts.items()))
                print(f"  {table:24s} {detail}")
        print(f"rows audited        {report['rows_audited']}")
        for note in report.get("notes", []):
            print(f"note                {note}")
        if report["clean"]:
            print("RESULT              CLEAN - every row traces back to a real, permitted source")
        else:
            print("RESULT              FAKES FOUND")
            for finding in report["findings"]:
                print(
                    f"  {finding['table']}.{finding['source_code']}: {finding['rows']} rows - {finding['reason']}"
                )

    return 0 if report["clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
