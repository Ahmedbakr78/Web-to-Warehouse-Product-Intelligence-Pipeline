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
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "docs" / "stats.json"

#: Keys whose value legitimately differs per run and must not be pinned.
#: The test count moves with every new test case and the diagram count with
#: every new diagram, so pinning either would mean the gate fails on every
#: commit that adds one. The exact numbers live in the generated statistics
#: block in README.md, which is checked separately by `--check-readme`.
VOLATILE = {"test_cases", "mermaid_diagrams"}

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


#: The figures that appear in prose, with the pattern that quotes them, and
#: the values that were once correct. Only a *stale* value is a problem: a
#: document that says "5 dimensions, 2 facts" is quoting a subset, not the
#: total, and must not be reported as drift.
PROSE_FIGURES: tuple[tuple[str, str, tuple[int, ...]], ...] = (
    ("physical_tables", r"(\d+)\s+(?:physical\s+)?tables\b", (23, 25, 28)),
    ("analytical_views", r"(\d+)\s+analytical\s+views\b", (20,)),
    ("rest_route_decorators", r"(\d+)\s+REST\s+(?:route\s+decorators|operations)\b", (113, 173, 194, 216)),
    ("data_quality_rules", r"(\d+)\s+data-quality\s+rules\b", ()),
    ("ingestion_sources", r"(\d+)\s+(?:ingestion\s+sources|source\s+adapters)\b", (5, 35)),
    ("airflow_tasks", r"(\d+)\s+Airflow\s+tasks\b", ()),
    ("mermaid_diagrams", r"(\d+)\s+Mermaid\s+diagrams\b", (80, 88, 99)),
)


def _prose_files() -> list[Path]:
    """The documents whose figures are pinned."""
    files = [ROOT / "README.md", ROOT / "docs" / "README.md"]
    files.extend(sorted((ROOT / "docs").glob("*.md")))
    return [path for path in files if path.is_file()]


#: The generated statistics block is written by `project_stats.py --sync-readme`
#: and verified separately by `project_stats.py --check-readme`. Scanning it here
#: as well would report the block as stale on every commit that changes a
#: figure, which is exactly the noise this check exists to avoid.
_STATS_BLOCK = re.compile(r"<!--\s*BEGIN:STATS\s*-->.*?<!--\s*END:STATS\s*-->", re.S)


def _strip_generated_block(text: str) -> str:
    """Remove the generated statistics block from a document."""
    return _STATS_BLOCK.sub("", text)


def check_prose(recorded: dict) -> list[str]:
    """Find a pinned figure that a document still quotes with an old value.

    The check is deliberately narrow: it only looks for the *current* value in
    a sentence that quotes a figure, and reports the documents that mention a
    *different* value for the same thing. A document that never mentions the
    figure is not a problem, and a document that mentions it correctly is
    not a problem.
    """
    import re

    problems: list[str] = []
    files = _prose_files()
    for key, pattern, stale in PROSE_FIGURES:
        value = recorded.get(key)
        if not isinstance(value, int) or value <= 0:
            continue
        stale_values = {item for item in stale if item != value}
        if not stale_values:
            continue
        for path in files:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            # A figure can be split across a line break ("28\ntables"), so
            # the text is searched with its whitespace collapsed.
            flat = re.sub(r"\s+", " ", _strip_generated_block(text))
            for match in re.finditer(pattern, flat):
                quoted = int(match.group(1))
                if quoted not in stale_values:
                    continue
                problems.append(
                    f"  {path.relative_to(ROOT)}: quotes {quoted} "
                    f"where the measured {DESCRIPTIONS.get(key, key)} is {value} "
                    f'-> "{match.group(0)}"'
                )
    return problems


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

    prose = check_prose(recorded)
    if prose:
        print("\nProse drift detected:\n")
        print("\n".join(prose))
        print(
            "\nThe pinned figures are also written into README.md and docs/*.md. "
            "Update the sentences that quote them, then run `make stats-update`."
        )
        return 1

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
