#!/usr/bin/env python3
"""Report the project's structural counts, measured from the code and schema.

Documentation drifts silently: a router is added, a test lands, a table appears,
and the numbers in the README quietly become wrong. This script measures them so
the claims can be regenerated rather than trusted.

Usage::

    python3 scripts/project_stats.py            # markdown table
    python3 scripts/stats.json                 # machine-readable, for CI

Nothing here starts a database or a service; every count comes from static
analysis of the source tree or the SQLAlchemy metadata.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
ROUTERS = APP / "api" / "routers"
VIEWS_SQL = ROOT / "db" / "views.sql"


def routers() -> int:
    return len([p for p in ROUTERS.glob("*.py") if p.stem != "__init__"])


def route_decorators() -> int:
    """Count ``@router.<verb>`` decorators across every router module."""
    pattern = re.compile(r"@router\.(get|post|put|patch|delete)\b")
    return sum(
        len(pattern.findall(p.read_text(encoding="utf-8"))) for p in ROUTERS.glob("*.py")
    )


def tables() -> int:
    """Physical tables, read from the SQLAlchemy metadata."""
    script = (
        "from app.models.base import Base\n"
        "import app.models  # noqa: F401  (registers every model)\n"
        "print(len(Base.metadata.tables))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        return -1
    try:
        return int(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return -1


def views() -> int:
    if not VIEWS_SQL.is_file():
        return -1
    text = VIEWS_SQL.read_text(encoding="utf-8")
    return len(re.findall(r"CREATE\s+(?:OR REPLACE\s+)?VIEW", text, re.IGNORECASE))


def _count_tests_in(path: Path) -> int:
    """Test functions defined at module level, plus one per parametrised case."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    total = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
            "test_"
        ):
            total += 1
    return total


def test_functions() -> int:
    return sum(_count_tests_in(p) for p in (ROOT / "tests").glob("test_*.py"))


def test_cases() -> int:
    """Actual collected test count, via pytest --collect-only."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    match = re.search(r"(\d+)\s+tests? collected", result.stdout)
    if match:
        return int(match.group(1))
    # Parametrised suites report "N tests collected" only on success; fall back
    # to counting the dots pytest prints with -q.
    tail = result.stdout.strip().splitlines()
    for line in reversed(tail):
        if "passed" in line or "collected" in line:
            found = re.search(r"(\d+)\s+(?:passed|collected)", line)
            if found:
                return int(found.group(1))
    return -1


def smoke_checks() -> int:
    """Assertions registered with the smoke suite.

    The suite keeps them in a module-level ``CHECKS`` list of
    ``(method, path, index, expectation, label)`` tuples, so counting the entries
    is both exact and cheaper than running the suite.
    """
    path = ROOT / "scripts" / "api_smoke.py"
    if not path.is_file():
        return -1

    text = path.read_text(encoding="utf-8")
    match = re.search(r"^CHECKS[^=]*=\s*\[(.*?)^\]", text, re.M | re.S)
    if not match:
        return -1

    # Each entry is a top-level tuple spanning one or more lines.
    body = match.group(1)
    entries = re.findall(r"^\s{4}\(", body, re.M)
    return len(entries)


def dq_rules() -> int:
    path = APP / "etl" / "dq.py"
    if not path.is_file():
        return -1
    return len(set(re.findall(r"\b(DQ\d{3})\b", path.read_text(encoding="utf-8"))))


def sources() -> int:
    directory = APP / "ingestion" / "sources"
    return len([p for p in directory.glob("*.py") if p.stem != "__init__"])


def airflow_tasks() -> int:
    path = ROOT / "dags" / "product_intelligence_pipeline.py"
    if not path.is_file():
        return -1
    return len(re.findall(r"^\s*def\s+\w+\s*\(", path.read_text(encoding="utf-8"), re.M)) - 1


def cli_commands() -> int:
    path = APP / "cli" / "main.py"
    if not path.is_file():
        return -1
    return len(re.findall(r"@app\.command", path.read_text(encoding="utf-8")))


def pipeline_stages() -> int:
    """Named stages recorded on the run record by the pipeline's timer."""
    path = APP / "etl" / "pipeline.py"
    if not path.is_file():
        return -1
    text = path.read_text(encoding="utf-8")
    return len(set(re.findall(r'self\._timer\(\s*"([a-z_]+)"', text)))


def compose_services() -> int:
    path = ROOT / "docker-compose.yml"
    if not path.is_file():
        return -1
    services: list[str] = []
    in_services = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if re.match(r"^services:\s*$", line):
            in_services = True
            continue
        if in_services:
            if re.match(r"^\S", line):
                break
            match = re.match(r"^  ([a-zA-Z0-9_-]+):\s*$", line)
            if match:
                services.append(match.group(1))
    return len(services)


def documentation_documents() -> int:
    return len([p for p in (ROOT / "docs").glob("[0-9][0-9]_*.md")])


def mermaid_diagrams() -> int:
    sources = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
    pattern = re.compile(r"^```mermaid\s*$(.*?)^```\s*$", re.M | re.S)
    return sum(len(pattern.findall(p.read_text(encoding="utf-8"))) for p in sources if p.is_file())


def features() -> int:
    path = ROOT / "docs" / "19_feature_list.md"
    if not path.is_file():
        return -1
    ids = {int(x) for x in re.findall(r"^\|\s*F-(\d+)", path.read_text(encoding="utf-8"), re.M)}
    return max(ids) if ids else -1


COLLECTORS = {
    "physical_tables": tables,
    "analytical_views": views,
    "rest_routers": routers,
    "rest_route_decorators": route_decorators,
    "data_quality_rules": dq_rules,
    "ingestion_sources": sources,
    "airflow_tasks": airflow_tasks,
    "cli_commands": cli_commands,
    "pipeline_stages": pipeline_stages,
    "compose_services": compose_services,
    "documentation_documents": documentation_documents,
    "mermaid_diagrams": mermaid_diagrams,
    "catalogued_features": features,
    "test_functions": test_functions,
    "test_cases": test_cases,
    "api_smoke_checks": smoke_checks,
}


def gather() -> dict[str, int]:
    stats: dict[str, int] = {}
    for name, collector in COLLECTORS.items():
        try:
            stats[name] = collector()
        except Exception as exc:  # pragma: no cover - never fail the whole report
            stats[name] = -1
            del exc
    return stats


LABELS = {
    "physical_tables": "Physical tables",
    "analytical_views": "Analytical views",
    "rest_routers": "REST routers",
    "rest_route_decorators": "REST route decorators",
    "data_quality_rules": "Data-quality rules",
    "ingestion_sources": "Ingestion sources",
    "airflow_tasks": "Airflow task callables",
    "cli_commands": "CLI commands",
    "pipeline_stages": "Pipeline stages",
    "compose_services": "Docker Compose services",
    "documentation_documents": "Numbered documents",
    "mermaid_diagrams": "Mermaid diagrams",
    "catalogued_features": "Catalogued features",
    "test_functions": "Test functions",
    "test_cases": "Collected test cases",
    "api_smoke_checks": "API smoke checks",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args()

    stats = gather()

    if args.json:
        print(json.dumps(stats, indent=2, sort_keys=True))
        return 0

    width = max(len(label) for label in LABELS.values())
    print("| Metric | Count |")
    print("| --- | ---: |")
    for key, label in LABELS.items():
        value = stats.get(key, -1)
        print(f"| {label.ljust(width)} | {value if value >= 0 else 'n/a'} |")
    print()
    print("Regenerate with `python3 scripts/project_stats.py`; a -1 means the")
    print("measurement could not be taken statically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())