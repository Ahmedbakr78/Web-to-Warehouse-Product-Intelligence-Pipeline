"""Concrete ingestion sources (free, public, automation-permitted endpoints).

Importing this package registers every source with the global registry.
"""

from __future__ import annotations

from app.ingestion.sources import (  # noqa: F401
    books_to_scrape,
    dummyjson,
    fakestore,
    local_fixture,
    openlibrary,
)

__all__ = [
    "dummyjson",
    "fakestore",
    "openlibrary",
    "books_to_scrape",
    "local_fixture",
]
