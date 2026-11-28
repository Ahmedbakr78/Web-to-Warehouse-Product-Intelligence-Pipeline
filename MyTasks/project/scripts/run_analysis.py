#!/usr/bin/env python3
"""Run the SQL analysis scripts in ``db/analysis`` and print readable tables.

    python scripts/run_analysis.py                      # every script, PostgreSQL
    python scripts/run_analysis.py -d mysql             # against MySQL
    python scripts/run_analysis.py 01_price_changes.sql  # a single script
    python scripts/run_analysis.py --json               # machine readable output

Bind parameters (``:since``, ``:row_limit``, ``:gap_pct``) are substituted for you, so the
scripts run identically on PostgreSQL, MySQL and SQLite.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.core.db import session_scope  # noqa: E402

GREEN, RED, CYAN, DIM, BOLD, NC = ("\033[0;32m", "\033[0;31m", "\033[0;36m", "\033[2m", "\033[1m", "\033[0m")

ANALYSIS_DIR = ROOT / "db" / "analysis"

#: Bind parameters with dialect-independent defaults.
#:
#: `:since` is the inclusive lower bound used by every dated script. `:days` is
#: accepted as an alias because the per-file headers document a window in days;
#: binding both means a script written against either name runs unchanged.
DEFAULT_PARAMS: dict[str, Any] = {
    "since": dt.date.today() - dt.timedelta(days=30),
    "days": 30,
    "row_limit": 25,
    "gap_pct": 1.0,
}


def split_statements(sql: str) -> list[str]:
    """Split a script into statements, keeping comments attached to their statement."""
    statements: list[str] = []
    buffer: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buffer.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(buffer))
            buffer = []
    if buffer:
        statements.append("\n".join(buffer))
    return statements


def bind(statement: str, params: dict[str, Any]) -> str:
    """Replace ``:name`` placeholders with a quoted literal.

    Substituting in Python (instead of using driver-level binds) keeps the scripts
    portable: some analytical statements repeat the same placeholder more than once, which
    not every driver's dict-binding supports.
    """
    rendered = statement
    for name, value in params.items():
        literal = str(value) if isinstance(value, (int, float)) else f"'{value}'"
        rendered = rendered.replace(f":{name}", literal)
    return rendered


def print_table(columns: list[str], rows: list[tuple], title: str) -> None:
    print(f"\n{BOLD}{title}{NC}")
    if not rows:
        print(f"{DIM}  (no rows){NC}")
        return
    widths = [len(str(column)) for column in columns]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = min(46, max(widths[index], len(_cell(cell))))
    header = "  ".join(str(column).ljust(widths[index]) for index, column in enumerate(columns))
    print(f"{CYAN}{header}{NC}")
    print(f"{DIM}{'  '.join('-' * width for width in widths)}{NC}")
    for row in rows:
        print("  ".join(_cell(cell).ljust(widths[index]) for index, cell in enumerate(row)))


def _cell(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, dt.datetime):
        return value.isoformat(sep=" ")[:19]
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)[:46]


def run(database: str, only: str | None, as_json: bool, limit: int, days: int | None = None) -> int:
    if not ANALYSIS_DIR.exists():
        print(f"{RED}No analysis directory at {ANALYSIS_DIR}{NC}")
        return 2

    files = sorted(ANALYSIS_DIR.glob("*.sql"))
    if only:
        files = [path for path in files if path.name.startswith(only)]
    if not files:
        print(f"{RED}No analysis script matches '{only}'{NC}")
        return 2

    params = dict(DEFAULT_PARAMS)
    params["row_limit"] = limit
    if days is not None:
        # `--days` shifts both the window name and the bound date together.
        params["days"] = days
        params["since"] = dt.date.today() - dt.timedelta(days=days)
    payload: dict[str, Any] = {}
    failures = 0

    for path in files:
        statements = split_statements(path.read_text(encoding="utf-8"))
        print(f"\n{BOLD}{'=' * 78}{NC}\n{BOLD}{path.name}{NC}{BOLD}{'=' * 78}{NC}")
        results_for_file: list[dict[str, Any]] = []
        with session_scope(database) as session:
            for index, statement in enumerate(statements, start=1):
                rendered = bind(statement, params)
                try:
                    result = session.execute(sa.text(rendered))
                    columns = list(result.keys())
                    rows = [tuple(row) for row in result.fetchall()]
                except Exception as exc:
                    failures += 1
                    print(f"{RED}  statement {index} failed:{NC} {str(exc).splitlines()[0][:180]}")
                    continue
                if as_json:
                    results_for_file.append(
                        {
                            "statement": index,
                            "columns": columns,
                            "rows": [list(row) for row in rows],
                        }
                    )
                else:
                    print_table(columns, rows, title=f"statement {index} · {len(rows)} rows")
        if as_json:
            payload[path.name] = results_for_file

    if as_json:
        print(json.dumps(payload, default=str, indent=2))
    else:
        target = settings.url_for(database)
        host = target.split("@")[-1]
        print(f"\n{GREEN}{'=' * 78}{NC}")
        print(f"{GREEN}  {len(files)} analysis scripts executed against {host}{NC}")
        if failures:
            print(f"{RED}  {failures} statement(s) failed{NC}")
        print(f"{GREEN}{'=' * 78}{NC}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute the SQL analysis scripts")
    parser.add_argument("--database", "-d", default=None, help="postgres | mysql | sqlite")
    parser.add_argument("script", nargs="?", default=None, help="script prefix, e.g. 01_price")
    parser.add_argument("--limit", "-l", type=int, default=25, help="value for :row_limit")
    parser.add_argument(
        "--days", "-w", type=int, default=None, help="window in days for :since / :days (default 30)"
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of tables")
    args = parser.parse_args()
    return run(
        (args.database or settings.active_database).lower(), args.script, args.json, args.limit, args.days
    )


if __name__ == "__main__":
    sys.exit(main())
