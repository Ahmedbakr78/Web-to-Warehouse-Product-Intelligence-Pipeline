#!/usr/bin/env python3
"""Fail CI when a structural figure quoted in the docs has drifted from reality.

``scripts/project_stats.py`` measures the counts; this compares them against the
snapshot committed at ``docs/stats.json`` and reports every difference.

The snapshot is deliberately a separate, small file rather than a number buried
in prose. When the codebase grows, the workflow is:

1. CI fails and prints exactly which figures changed.
2. Update the prose in the README and the affected documents.
3. Run ``make stats-update`` to refresh the snapshot, and commit both together.

That turns "the README says 23 tables" from a claim nobody re-checks into a
value with an owner and a diff.

Usage::

    python3 scripts/check_stats.py docs/stats.json [--write]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "docs" / "stats.json"

#: Keys whose value legitimately differs per run and must not be pinned.
VOLATILE = {"test_cases"}

#: How each key should be described when reporting a drift.
DESCRIPTIONS = {
    "physical_tables": "physical tables in the warehouse",
    "analytical_views": "analytical views in db/views.sql",
    "rest_routers": "REST routers",
    "rest_route_decorators": "REST route decorators",
    "data_quality_rules": "data-quality rules",
    "ingestion_sources": "ingestion source adapters",
    "airflow_tasks": "Airflow task callables",
    "cli_commands": "CLI commands",
    "pipeline_stages": "pipeline stages",
    "compose_services": "Docker Compose services",
    "documentation_documents": "numbered documentation documents",
    "mermaid_diagrams": "Mermaid diagrams",
    "catalogued_features": "catalogued features",
    "test_functions": "test functions",
    "api_smoke_checks": "API smoke checks",
}


def measure() -> dict[str, int]:
    """Current counts, via project_stats.py."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "project_stats.py"), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit("project_stats.py failed")
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("snapshot", nargs="?", default="docs/stats.json")
    parser.add_argument(
        "--write",
        action="store_true",
        help="rewrite the snapshot instead of comparing (make stats-update)",
    )
    args = parser.parse_args()

    target = Path(args.snapshot)
    if not target.is_absolute():
        target = ROOT / target

    current = measure()

    if args.write:
        payload = {
            "_comment": (
                "Structural counts measured by scripts/project_stats.py. "
                "Update with `make stats-update` in the same commit as any prose "
                "that quotes these figures."
            ),
            **current,
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Wrote {target.relative_to(ROOT)}")
        return 0

    if not target.is_file():
        print(
            f"error: {target.relative_to(ROOT)} is missing.\nCreate it once with:  make stats-update",
            file=sys.stderr,
        )
        return 2

    recorded = json.loads(target.read_text(encoding="utf-8"))

    drift: list[str] = []
    unmeasured: list[str] = []

    for key, value in sorted(current.items()):
        if key in VOLATILE:
            continue
        if value < 0:
            unmeasured.append(key)
            continue
        if key not in recorded:
            drift.append(f"  + {DESCRIPTIONS.get(key, key)}: not in the snapshot (now {value})")
            continue
        old = recorded[key]
        if old != value:
            arrow = "+" if value > old else "-"
            drift.append(
                f"  {arrow} {DESCRIPTIONS.get(key, key)}: {old} -> {value}  "
                f"(update the prose, then run `make stats-update`)"
            )

    if unmeasured:
        print("Not measurable statically (skipped): " + ", ".join(unmeasured))

    if drift:
        print("\nDocumentation drift detected:\n")
        print("\n".join(drift))
        print(
            "\nUpdate the figures quoted in README.md and docs/*.md, then run "
            "`make stats-update` and commit both changes together."
        )
        return 1

    print(f"No drift: all {len(current) - len(VOLATILE)} pinned figures match {target.relative_to(ROOT)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
