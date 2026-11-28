#!/usr/bin/env python
"""Propagate the canonical VERSION file to every place that advertises it.

`VERSION` at the project root is the single source of truth.  This script
rewrites the version field in `pyproject.toml` and `frontend/package.json`, and
fails loudly if anything else in the tree still hard-codes a different number.

Run it from `make version-sync` and from CI.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"

PYPROJECT_RE = re.compile(r'^(version\s*=\s*)"[^"]+"', re.MULTILINE)

# Files that legitimately contain no version literal.
IGNORED = {
    VERSION_FILE,
    ROOT / "package-lock.json",
    ROOT / "frontend" / "package-lock.json",
}


def canonical() -> str:
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?", version):
        raise SystemExit(f"VERSION is not a valid semantic version: {version!r}")
    return version


def sync_pyproject(version: str) -> bool:
    path = ROOT / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    updated, count = PYPROJECT_RE.subn(rf'\g<1>"{version}"', text, count=1)
    if count and updated != text:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def sync_package_json(version: str) -> bool:
    path = ROOT / "frontend" / "package.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") == version:
        return False
    payload["version"] = version
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return True


def find_strays(version: str) -> list[str]:
    """Report source files that still declare a different version literal."""
    pattern = re.compile(r"""\bversion\b\D{0,4}["'](\d+\.\d+\.\d+)["']""", re.IGNORECASE)
    offenders: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path in IGNORED:
            continue
        parts = set(path.parts)
        if parts & {
            ".venv",
            "node_modules",
            "dist",
            ".git",
            "var",
            "__pycache__",
            ".pytest_cache",
            ".ruff_cache",
            ".mypy_cache",
        }:
            continue
        if path.suffix not in {".py", ".ts", ".tsx", ".json", ".toml", ".cfg"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in pattern.finditer(content):
            if match.group(1) != version:
                offenders.append(f"{path.relative_to(ROOT)}: {match.group(0).strip()}")
                break
    return offenders


def main() -> int:
    version = canonical()
    changed = []
    if sync_pyproject(version):
        changed.append("pyproject.toml")
    if sync_package_json(version):
        changed.append("frontend/package.json")

    print(f"canonical version: {version}")
    print("updated: " + (", ".join(changed) if changed else "nothing (already in sync)"))

    strays = find_strays(version)
    if strays:
        print(f"\n{len(strays)} file(s) still advertise a different version:", file=sys.stderr)
        for offender in strays:
            print(f"  - {offender}", file=sys.stderr)
        return 1

    print("no stray version literals found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
