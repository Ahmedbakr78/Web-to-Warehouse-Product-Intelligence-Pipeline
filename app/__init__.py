"""Application package root for the Product Intelligence Pipeline.

The version is the single source of truth for the whole repository: the canonical
value lives in the ``VERSION`` file at the project root, and everything else
(`pyproject.toml`, the API's `/meta` and `/version` endpoints, the CLI `version`
command, the dashboard footer and the frontend package) reads it from there. That
removes the previous situation where four files each claimed a different number.
"""

from __future__ import annotations

from pathlib import Path

VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"


def _read_version() -> str:
    """Read the canonical version, falling back to a safe default."""
    try:
        value = VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"
    return value or "0.0.0"


__version__ = _read_version()
__all__ = ["VERSION_FILE", "__version__"]
