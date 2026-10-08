"""Shared ORDER BY assembly for the raw-SQL list endpoints.

`sort_by` / `sort_dir` accept comma-separated levels (``price,rating`` with
``asc,desc``); every level is checked against the endpoint's allowlist so user
input can never reach the SQL string. Unknown fields are dropped, missing
directions inherit the previous level, and an empty result falls back to the
endpoint default. Levels are capped so a hostile query cannot stack dozens of
sort keys. ``(col IS NULL) ASC`` keeps the portable NULLS-LAST behaviour on
both PostgreSQL and MySQL.
"""

from __future__ import annotations

MAX_SORT_LEVELS = 3


def build_order_by(
    sort_by: str | None,
    sort_dir: str | None,
    allowed: dict[str, str],
    default: str,
) -> str:
    """Return a safe ``ORDER BY ...`` fragment (without the keywords)."""
    fields = [part.strip().lower() for part in str(sort_by or "").split(",") if part.strip()]
    directions = [part.strip().lower() for part in str(sort_dir or "").split(",") if part.strip()]
    clauses: list[str] = []
    last_direction = "DESC"
    for index, field in enumerate(fields[:MAX_SORT_LEVELS]):
        column = allowed.get(field)
        if not column:
            continue
        if index < len(directions):
            last_direction = "ASC" if directions[index] == "asc" else "DESC"
        clauses.append(f"({column} IS NULL) ASC, {column} {last_direction}")
    if not clauses:
        clauses.append(f"({default} IS NULL) ASC, {default} DESC")
    return ", ".join(clauses)
